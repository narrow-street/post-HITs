
import os
import sys
import logging
import random
import string
import configparser


CONFIG_SECTIONS = {'INFO', 'SETUP', 'HITSET', 'NUM APPROVED', 'PERCENT APPROVED',
                   'LOCATION', 'EXCLUDE QUALIFICATION TYPE', 'INCLUDE QUALIFICATION TYPE', 'TEST'}


def make_mtc(account, host):
    import boto3
    # get property settings for HIT
    endpoint_url = get_endpoint_url(host)
    client_kwargs = dict(endpoint_url=endpoint_url,
                         region_name='us-east-1')

    APIkey_kwargs = get_APIkey(account)
    mtc = boto3.client('mturk', **client_kwargs, **APIkey_kwargs)
    return mtc


class ExternalQuestion:
    schema_url = "http://mechanicalturk.amazonaws.com/AWSMechanicalTurkDataSchemas/2006-07-14/ExternalQuestion.xsd"
    template = '<ExternalQuestion xmlns="%(schema_url)s"><ExternalURL>%%(external_url)s</ExternalURL><FrameHeight>%%(frame_height)s</FrameHeight></ExternalQuestion>' % vars()

    def __init__(self, external_url, frame_height=675):
        self.external_url = external_url
        self.frame_height = frame_height

    def get_as_params(self, label='ExternalQuestion'):
        return {label: self.get_as_xml()}

    def get_as_xml(self):
        return self.template % vars(self)


def is_confirmed(notice):
    response = input(notice).lower()
    response_is_valid = False

    while not response_is_valid:
        if response in ['y', 'yes', '1']:
            response_is_valid = True
            return True
        elif response in ['n', 'no', '0']:
            response_is_valid = True
            return False
        else:
            respond_again_notice = 'Your response is not accepted. Please enter either "y" or "n": '
            response = input(respond_again_notice).lower()


def set_logging_configs(module_name, stream=True, save_log_path=None):
    # logging configurations
    logger = logging.getLogger(module_name)
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s:%(name)s:%(message)s')

    # print logging info
    if stream:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    # save logging info into a file
    if save_log_path:
        file_handler = logging.FileHandler(save_log_path)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def check_file_exists(project_path, file_name):

    file_path = os.path.join(project_path, file_name)
    if not os.path.exists(file_path):
        raise FileNotFoundError('%s not found' % file_path)


def get_hit_url(project_name, experimenter, landing_file):
    base = 'https://scorsese.wjh.harvard.edu/turk/experiments/'
    return '%s/%s/%s/%s' % (base, experimenter, project_name, landing_file)


def get_endpoint_url(host):
    if host == 'sandbox':
        return "https://mturk-requester-sandbox.us-east-1.amazonaws.com"
    elif host == 'formal':
        return "https://mturk-requester.us-east-1.amazonaws.com"
    else:
        raise RuntimeError(
            'INPUT host "%s" does not exist, please use "sandbox" or "formal".' % host)


def get_preview_url(host):
    if host == 'sandbox':
        return "https://workersandbox.mturk.com/mturk/preview"
    elif host == 'formal':
        return "https://www.mturk.com/mturk/preview"
    else:
        raise RuntimeError(
            'INPUT host "%s" does not exist, please use "sandbox" or "formal".' % host)


def get_APIkey(account):
    import sys
    sys.path.append('/Volumes/turk/boto')

    if account == "alvarezlab":
        from alvarezlab import ACCESS_ID, SECRET_KEY
    elif account == "konklab":
        from konklab import ACCESS_ID, SECRET_KEY
    else:
        raise RuntimeError(
            'The INPUT account "%s" does not exist, please use "konklab" or "alvarezlab".' % account)

    return dict(aws_access_key_id=ACCESS_ID, aws_secret_access_key=SECRET_KEY)


def read_config(project_path, config_file):
    config_file = os.path.join(project_path, config_file)

    config = configparser.ConfigParser()
    config.read(config_file)

    try:
        assert(set(config.sections()) <= CONFIG_SECTIONS)
    except AssertionError as err:
        err.args += ("CONFIG file section names are incorrect.",)
        raise
    else:
        return config


def underscore_to_camel(string):
    return ''.join(map(lambda x: x.capitalize(), string.split('_')))


def get_hit_descriptions(config):
    key_value_pairs = {underscore_to_camel(k): config[k] for k in config}
    # check description kwargs
    keys = {'Description', 'Keywords', 'Title'}
    try:
        assert(set(key_value_pairs.keys()) == keys)
    except AssertionError as err:
        err.args += ("CONFIG file DESCRIPTION fields are incorrect.",)
        raise
    else:
        return key_value_pairs


def get_hit_setups(config):
    def min2sec(x): return int(x) * 60
    def hour2sec(x): return int(x) * 3600

    reformater = dict(
        LifetimeInHours=('LifetimeInSeconds', hour2sec),
        AssignmentDurationInMins=('AssignmentDurationInSeconds', min2sec),
        AutoApprovalDelayInHours=('AutoApprovalDelayInSeconds', hour2sec),
        MaxAssignments=('MaxAssignments', int)
    )

    key_val_pairs = {underscore_to_camel(
        k): config[k] for k in config}

    for old_key, (new_key, func) in reformater.items():
        value = key_val_pairs.pop(old_key)
        key_val_pairs[new_key] = func(value)

    # check description kwargs
    keys = {'AssignmentDurationInSeconds', 'AutoApprovalDelayInSeconds',
            'LifetimeInSeconds', 'MaxAssignments', 'Reward'}
    try:
        assert(set(key_val_pairs.keys()) == keys)
    except AssertionError as err:
        err.args += ("CONFIG file SETUP fields are incorrect.",)
        raise
    else:
        return key_val_pairs


def get_qualification_requirements(qualification, config):

    qr_dict = dict(ActionsGuarded='DiscoverPreviewAndAccept')

    if qualification == 'percent_assignments_approved':
        qr_dict['QualificationTypeId'] = '000000000000000000L0'
        qr_dict['Comparator'] = 'GreaterThanOrEqualTo'
        qr_dict['IntegerValues'] = [int(config['percent'])]

    elif qualification == 'num_hit_approved':
        qr_dict['QualificationTypeId'] = '00000000000000000040'
        qr_dict['Comparator'] = 'GreaterThanOrEqualTo'
        qr_dict['IntegerValues'] = [int(config['num'])]

    elif qualification == 'location':
        qr_dict['QualificationTypeId'] = '00000000000000000071'
        qr_dict['Comparator'] = 'EqualTo'
        qr_dict['LocaleValues'] = [dict(Country=config['country'])]

    elif qualification == 'exclude_qualification_type':
        qr_dict['QualificationTypeId'] = config['id']
        qr_dict['Comparator'] = 'DoesNotExist'

    elif qualification == 'include_qualification_type':
        qr_dict['QualificationTypeId'] = config['id']
        qr_dict['Comparator'] = 'Exists'
    else:
        raise RuntimeError('The qualification input is incorrect')

    return qr_dict


def get_hit_set_ids(config):
    HSetId_str = config['HSetId']
    return parse_HSetId_str(HSetId_str)


def parse_HSetId_str(HSetId_str):
    import re

    if HSetId_str.isdigit():
        return [int(HSetId_str)]

    elif re.match(r'^\d+:\d+$', HSetId_str):
        start_id, end_id = HSetId_str.split(':')
        return list(range(int(start_id), int(end_id) + 1))

    elif re.match(r'^\d+-\d+$', HSetId_str):
        start_id, end_id = HSetId_str.split('-')
        return list(range(int(start_id), int(end_id) + 1))

    elif re.match(r'\d+(,\d+)+$', HSetId_str):
        return [int(i) for i in HSetId_str.split(',')]

    else:
        raise RuntimeError('CONFIG file HSetId is incorrect.')


def get_review(name, param, mtc=None):
    if name == 'description':
        return ("\nDescribe your task to Workers ...\n" +
                '    Title       : %s\n' % param["title"] +
                '    Description : %s\n' % param["description"] +
                '    Keywords    : %s\n' % param["keywords"])

    elif name == 'setup':
        return ("\nSetting up your task ...\n" +
                '    Reward per assignment           :  %s $\n' % param["reward"] +
                '    Number of assignments per task  :  %s\n' % param["max_assignments"] +
                '    Time allotted per assignment    :  %s Minutes\n' % param["assignment_duration_in_mins"] +
                '    Task expires in                 :  %s Hours\n' % param["lifetime_in_hours"] +
                '    Auto-approve and pay Workers in :  %s Hours\n' % param["auto_approval_delay_in_hours"])

    elif name == 'percent_assignments_approved':
        return "    HIT Approval Rate (%%) for all Requesters' HITs : %s %%\n" % param['percent']

    elif name == 'num_hit_approved':
        return "    Number of HITs Approved                        : %s\n" % param['num']

    elif name == 'location':
        return "    Location                                       : %s\n" % param['country']

    elif name.endswith('qualification_type'):
        qt_id = param['id']
        qt_name = mtc.get_qualification_type(QualificationTypeId=qt_id)[
            'QualificationType']['Name']
        qt_num = mtc.list_workers_with_qualification_type(
            QualificationTypeId=qt_id, MaxResults=100)['NumResults']
        # the max number of results that boto3 allowed is 100
        qt_num_str = str(qt_num) if qt_num < 100 else 'more than 100'

        if name.startswith('exclude'):
            task = 'excluded'
        elif name.startswith('include'):
            task = 'included'
        return "    You've %s %s Workers with **%s**.\n" % (task, qt_num_str, qt_name)
    else:
        raise RuntimeError('The INPUT of qualification is incorrect')


def get_aws_shell_list_hits(HITGroupId, host, max_results=5):
    command = ("mturk list-hits --output table --query 'HITs[?HITGroupId==`PLACEHOLDER`]" +
               ".{\"1. HITId\": HITId, \"2. Title\": Title, \"3. Status\": HITStatus, " +
               "\"4.Num Total\": MaxAssignments, \"5.Num Pending\": NumberOfAssignmentsPending, "
               "\"6.Num Completed\": NumberOfAssignmentsCompleted}\'")

    if host == 'sandbox':
        command += " --endpoint-url https://mturk-requester-sandbox.us-east-1.amazonaws.com"

    return command.replace('PLACEHOLDER', HITGroupId)


def get_aws_shell_list_assignments(HITIds, host):
    command = ('mturk list-assignments-for-hit --hit-id PLACEHOLDER --query "Assignments[].' +
               '{AssignmentId: AssignmentId, Status: AssignmentStatus, WorkerId: WorkerId}" --output "table"')
    if host == 'sandbox':
        command += " --endpoint-url https://mturk-requester-sandbox.us-east-1.amazonaws.com"
    return '\n'.join([command.replace('PLACEHOLDER', id_) for id_ in HITIds])
