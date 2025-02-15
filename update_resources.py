import os
import sys
import re
import argparse
import urllib3
import certifi
import requests
import subprocess
import hashlib
import time
import glob
import avinput2annovardb

# connect to a distant resource and check whether or
# not we should update - and updates


def log(level, text):
    localtime = time.asctime(time.localtime(time.time()))
    if level == 'ERROR':
        sys.exit('[{0}]: {1} - {2}'.format(level, localtime, text))
    print('[{0}]: {1} - {2}'.format(level, localtime, text))


def get_last_md5_file(resource_dir, resource_type, resource_regexp, target_suffix):
    files = os.listdir(resource_dir)
    dates = []
    for current_file in files:
        # print(current_file)
        match_obj = re.search(rf'{resource_regexp}{target_suffix}.gz.md5$', current_file)
        if match_obj:
            dates.append(match_obj.group(1))
    if dates:
        current_resource = '{0}{1}_{2}{3}.gz.md5'.format(resource_dir, resource_type, max(dates), target_suffix)
        with open(current_resource, 'r') as current_file:
            # print(clinvar_file.read())
            match_obj = re.search(r'^(\w+)\s', current_file.read())
            if match_obj:
                return match_obj.group(1), max(dates)
    return 'no previous file', 1

# from https://www.techcoil.com/blog/how-to-download-a-file-via-http-post-and-http-get-with-python-3-requests-library/


def download_file_from_server_endpoint(server_endpoint, local_file_path):
    # Send HTTP GET request to server and attempt to receive a response
    response = requests.get(server_endpoint)
    # If the HTTP GET request can be served
    # log('DEBUG', response.status_code)
    if response.status_code == 200:
        # Write the file contents in the response to a file specified by local_file_path
        try:
            log('INFO', 'Downloading file as {}'.format(local_file_path))
            with open(local_file_path, 'wb') as local_file:
                for chunk in response.iter_content(chunk_size=128):
                    local_file.write(chunk)
            # log('DEBUG', 'Downloaded file as {}'.format(local_file_path))
        except Exception:
            log('WARNING', 'Unable to download {}'.format(server_endpoint))
    else:
        log('WARNING', 'Unable to contact {}'.format(server_endpoint))


def get_new_ncbi_resource_file(http, resource_type, resource_dir, regexp, label, url, target_suffix):
    distant_md5 = None
    download_semaph = None
    resource_dir_content = None
    # log('DEBUG', '{0}{1}.gz'.format(regexp, target_suffix))
    try:
        # Get all file names from clinvar website (html)
        resource_dir_html = http.request('GET', url).data.decode('utf-8')
        resource_dir_content = re.split('\n', resource_dir_html)
        resource_date = "20190101"
        last_obj = None
        for html in resource_dir_content:
            match_obj = re.search(rf'\"{regexp}{target_suffix}.gz\"', html)
            if match_obj:
                # first is last
                tmp_date = match_obj.group(1)
                if time.strptime(tmp_date, "%Y%m%d") >= time.strptime(resource_date, "%Y%m%d"):
                    resource_date = tmp_date
                    last_obj = match_obj
    except Exception:
        log('WARNING', 'Unable to contact {0} {1}'.format(label, url))
        return 0, 0, 0
    if last_obj:
        resource_date = last_obj.group(1)
        # Read current clinvar md5
        try:
            resource_md5 = http.request(
                'GET',
                '{0}{1}_{2}{3}.gz.md5'.format(url, resource_type, resource_date, target_suffix)
            ).data.decode('utf-8')
            match_obj = re.search(r'^(\w+)\s', resource_md5)
            if match_obj:
                distant_md5 = match_obj.group(1)
                log('INFO', '{0} distant md5: {1}'.format(label, distant_md5))
        except Exception:
            log('WARNING', 'Unable to contact {0} md5 {1}'.format(label, url))
            return 0, 0, 0
        if distant_md5:
            # Get md5 from local file
            # current_md5_value = get_last_clinvar_md5_file('{}clinvar/hg38/'.format(resources_path))
            current_md5_value, last_version = get_last_md5_file(resource_dir, resource_type, regexp, target_suffix)
            log('INFO', '{0} local md5: {1}'.format(label, current_md5_value))
            if current_md5_value != distant_md5:
                # Download remote file
                # log('DEBUG', '{0}{1}_{2}{3}.gz'.format(url, resource_type, resource_date, target_suffix))
                # log('DEBUG', resource_dir)
                # log('DEBUG', '{0}{1}_{2}{3}.gz'.format(resource_dir, resource_type, resource_date, target_suffix))
                # try:
                download_file_from_server_endpoint(
                    '{0}{1}_{2}{3}.gz'.format(url, resource_type, resource_date, target_suffix),
                    '{0}{1}_{2}{3}.gz'.format(resource_dir, resource_type, resource_date, target_suffix)
                )
                download_file_from_server_endpoint(
                    '{0}{1}_{2}{3}.gz.md5'.format(url, resource_type, resource_date, target_suffix),
                    '{0}{1}_{2}{3}.gz.md5'.format(resource_dir, resource_type, resource_date, target_suffix)
                )
                download_file_from_server_endpoint(
                    '{0}{1}_{2}{3}.gz.tbi'.format(url, resource_type, resource_date, target_suffix),
                    '{0}{1}_{2}{3}.gz.tbi'.format(resource_dir, resource_type, resource_date, target_suffix)
                )
                download_semaph = 1
                # Then check new md5 and test w/ a variant
                if download_semaph == 1:
                    with open(
                        '{0}{1}_{2}{3}.gz'.format(resource_dir, resource_type, resource_date, target_suffix), 'rb'
                    ) as new_resource_file:
                        BLOCKSIZE = 65536
                        buf = new_resource_file.read(BLOCKSIZE)
                        hasher = hashlib.md5()
                        while len(buf) > 0:
                            hasher.update(buf)
                            buf = new_resource_file.read(BLOCKSIZE)
                        # log('DEBUG', hasher.hexdigest() )
                        if hasher.hexdigest() == distant_md5:
                            # Download successful
                            log(
                                'INFO',
                                'Successfully downloaded and checked {0} file {1}_{2}{3}.gz'.format(
                                    label, resource_type, resource_date, target_suffix
                                )
                            )
                            return '{0}_{1}{2}.gz'.format(resource_type, resource_date, target_suffix), last_version, resource_date
                        else:
                            # Remove old files
                            os.remove(
                                '{0}{1}_{2}{3}.gz'.format(
                                    resource_dir, resource_type, resource_date, target_suffix
                                )
                            )
                            os.remove(
                                '{0}{1}_{2}{3}.gz.md5'.format(
                                    resource_dir, resource_type, resource_date, target_suffix
                                )
                            )
                            os.remove(
                                '{0}{1}_{2}{3}.gz.tbi'.format(
                                    resource_dir, resource_type, resource_date, target_suffix
                                )
                            )
                            log(
                                'WARNING',
                                'Error in md5 sum for {0} file {0}_{1}{2}.gz'.format(
                                    resource_type, resource_date, target_suffix
                                )
                            )
                            return 0, 0, 0
        return 0, 0, 0


def main():
    parser = argparse.ArgumentParser(
        description='Checks for ANNOVAR resources distant updates and convert to ANNOVAR format',
        usage='python update_resources.py <-d clinvar> <-hp /path/to/annovar/humandb> <-g [GRCh37|GRCh38]> <-a path/to/annovar>'
    )
    parser.add_argument('-d', '--database-type', default='clinvar', required=True,
                        help='Database to update (e.g. clinvar)')
    parser.add_argument('-hp', '--humandb-path', default=None,
                        help='Final full path to the resource to update')
    parser.add_argument('-g', '--genome-version', default='GRCh37',
                        help='Genome version [GRCh37|GRCh38]')
    parser.add_argument('-a', '--annovar-path', required=True,
                        help='Full path to annovar dir')
    parser.add_argument('-r', '--rename', required=False,
                        help='A name to replace the date in the ANNOVAR db file, e.g. latest')
    parser.add_argument('-w', '--weekly', required=False, 
                        action='store_true', default=False,
                        help='Download weekly update clinvar vcf')
    args = parser.parse_args()

    # dbsnp_url = 'https://ftp.ncbi.nih.gov/snp/latest_release/'
    resources_path = None
    if args.humandb_path:
        resources_path = args.humandb_path
    if args.genome_version:
        genome_version = args.genome_version
        annovar_genome_version = 'hg19' if genome_version == 'GRCh37' else 'hg38'
        # creates clinvar/GRCh38 folder if does not exist
        if not os.path.isdir('clinvar/GRCh38'):
            os.mkdir('clinvar/GRCh38', 0o755)
    weekly_path = ""
    if args.weekly:
        weekly_path = "weekly/"
    clinvar_url = 'https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_{}/{}'.format(genome_version, weekly_path)
    if args.annovar_path:
        annovar_path = args.annovar_path
        if annovar_path and \
                not resources_path:
            resources_path = '{}/humandb'.format(annovar_path)
    new_name = None
    if args.rename:
        new_name = args.rename
    http = urllib3.PoolManager(cert_reqs='CERT_REQUIRED', ca_certs=certifi.where())
    if args.database_type:
        db_type = args.database_type
    # match_obj = None
    if db_type == 'clinvar' and \
            resources_path and \
            genome_version and \
            annovar_path:
        # http, resource_type, resource_dir, regexp, label, url, target_suffix
        new_file, last_version, resource_date = get_new_ncbi_resource_file(
            http,
            'clinvar',
            'clinvar/{0}/'.format(genome_version),
            r'clinvar_(\d+)',
            'ClinVar',
            clinvar_url,
            '.vcf'
        )
        if new_file is not None and \
                new_file != 0:
            current_path = os.path.dirname(os.path.realpath(__file__))
            # then we have to convert the file to annovar format
            # 1st step use convert2annovar.pl script then manually finish conversion
            log(
                'INFO',
                'Launching ANNOVAR convert2annovar on {}'.format(new_file)
            )
            avinput_file = os.path.splitext(os.path.splitext(new_file)[0])[0]
            log(
                'INFO',
                'Remove old version files.'
            )
            result = subprocess.run(
                [
                    'find',
                    resources_path,
                    '!',
                    '-name',
                    '*{}*'.format(avinput_file),
                    '-type',
                    'f',
                    '-exec',
                    'rm',
                    '-f',
                    '{}',
                    '+',
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT
            )
            if os.path.exists('{0}/{1}_{2}.txt.gz'.format(
                            resources_path, annovar_genome_version, avinput_file
                        )):
                log(
                    'INFO',
                    'The latest version existed. Finish.'
                )
                exit(0)
            result = subprocess.run(
                [
                    'perl',
                    '{}/convert2annovar.pl'.format(annovar_path),
                    '-format',
                    'vcf4',
                    '-includeinfo',
                    '{0}/clinvar/{1}/{2}'.format(current_path, genome_version, new_file),
                    '-outfile',
                    'clinvar/{0}/{1}.avinput'.format(genome_version, avinput_file)
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT
            )
            if result.returncode == 0:
                log(
                    'INFO',
                    'ANNOVAR successfully created clinvar/{0}/{1}.avinput'.format(genome_version, avinput_file)
                )
                log(
                    'INFO',
                    'Launching CUSTOM conversion to ANNOVAR db format on clinvar/{0}/{1}.avinput'.format(
                        genome_version, avinput_file
                    )
                )
                # the file needs to be formatted as an annovar db
                try:
                    annovar_db_file = avinput2annovardb.clinvaravinput2annovardb(
                        'clinvar/{0}/{1}.avinput'.format(genome_version, avinput_file),
                        ['ALLELEID', 'CLNDN', 'CLNDISDB', 'CLNREVSTAT', 'CLNSIG']
                    )
                    if new_name:
                        new_annovar_db_file = re.sub(r'_\d{8}\.', '_{}.'.format(new_name), annovar_db_file)
                        # create a file which keeps the last version
                        ver_file = open(
                            '{0}/{1}_clinvar_{2}.ver'.format(resources_path, annovar_genome_version, new_name),
                            "w"
                        )
                        ver_file.write('ClinVar:{0}\n'.format(resource_date))
                        ver_file.close()
                    else:
                        new_annovar_db_file = annovar_db_file
                except Exception:
                    log(
                        'ERROR',
                        'Failed in converting to ANNOVAR db format clinvar/{0}/{1}.avinput'.format(
                            genome_version, avinput_file
                        )
                    )
                    sys.exit(1)
                log(
                    'INFO',
                    'File successfully converted to ANNOVAR db format {}'.format(
                        new_annovar_db_file
                    )
                )
                log(
                    'INFO',
                    'Launching ANNOVAR indexing on {0}/{1}'.format(
                        resources_path, os.path.basename(new_annovar_db_file)
                    )
                )
                # run index_annovar.pl
                result_index = subprocess.run(
                    [
                        'perl',
                        '{}/index_annovar.pl'.format(annovar_path),
                        annovar_db_file,
                        '-outfile',
                        '{0}/{1}_{2}'.format(
                            resources_path, annovar_genome_version, os.path.basename(new_annovar_db_file)
                        ),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT
                )
                if result_index.returncode == 0:
                    log(
                        'INFO',
                        'ANNOVAR successfully indexed {0}/{1}'.format(
                            resources_path, os.path.basename(new_annovar_db_file)
                        )
                    )
                    result = subprocess.run(
                        [
                            'gzip'
                        ] + glob.glob('{0}/*.txt'.format(resources_path)) 
                        + glob.glob('{0}/*.idx'.format(resources_path)),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.STDOUT
                    )
                    if result.returncode == 0:
                        log(
                            'INFO',
                            'gzip compress for output files'
                        )
                    if last_version != 1:
                        # rm previous version
                        os.remove('clinvar/{0}/clinvar_{1}.vcf.gz'.format(genome_version, last_version))
                        os.remove('clinvar/{0}/clinvar_{1}.vcf.gz.tbi'.format(genome_version, last_version))
                        os.remove('clinvar/{0}/clinvar_{1}.vcf.gz.md5'.format(genome_version, last_version))
                        os.remove('clinvar/{0}/clinvar_{1}.avinput'.format(genome_version, last_version))
                        os.remove('clinvar/{0}/clinvar_{1}.txt'.format(genome_version, last_version))

    # not available
    # if args.dbsnp:
    #
    #     # get dbsnp version from https://ftp.ncbi.nih.gov/snp/latest_release/release_notes.txt
    #     download_file_from_server_endpoint(
    #         '{}release_notes.txt'.format(dbsnp_url),
    #         '{}dbsnp/release_notes.txt'.format(resources_path)
    #     )
    #     with open('{}dbsnp/release_notes.txt'.format(resources_path), 'r') as f:
    #         match_obj = re.search(r'dbSNP build (\d+) release notes', f.readline())
    #         semaph = 0
    #         if match_obj:
    #             dbsnp_version = match_obj.group(1)
    #             log('INFO', 'dbSNP version file found: v{0}'.format(dbsnp_version))
    #             if not os.path.exists('{0}/dbsnp/hg38/v{1}'.format(resources_path, dbsnp_version)):
    #                 os.makedirs('{0}/dbsnp/hg38/v{1}'.format(resources_path, dbsnp_version))
    #             else:
    #                 log('INFO', 'dbSNP version file found: v{0} same as current'.format(dbsnp_version))
    #                 semaph = 1
    #             # os.mkdir('{0}/dbsnp/v{1}'.format(resources_path, dbsnp_version))
    #         else:
    #             log('ERROR', 'Unable to donwload/read dbSNP release file from: '.format('{}release_notes.txt'.format(dbsnp_url)))
    #         if semaph == 0:
    #             # http, resource_type, resource_dir, regexp, label, url, target_suffix
    #             get_new_ncbi_resource_file(
    #                 http,
    #                 'GCF',
    #                 '{0}dbsnp/hg38/v{1}/'.format(resources_path, dbsnp_version),
    #                 r'GCF_(\d+)',
    #                 'dbSNP',
    #                 '{0}VCF/'.format(dbsnp_url),
    #                 '.38'
    #            )


if __name__ == '__main__':
    main()

# From https://www.pythoncentral.io/hashing-files-with-python/
# if we need to check a md5
# BLOCKSIZE = 65536
# with open('MobiDetailsApp/static/resources/clinvar/hg38/clinvar_20200310.vcf.gz', 'rb') as clinvar_file:
#      buf = clinvar_file.read(BLOCKSIZE)
#      while len(buf) > 0:
#          hasher.update(buf)
#          buf = clinvar_file.read(BLOCKSIZE)

# print(hasher.hexdigest())
