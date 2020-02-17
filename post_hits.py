"""
    publish HITs
"""

import os
import boto3

from helpers import (check_file_exists, set_logging_configs, read_config,
                     make_mtc, is_confirmed, ExternalQuestion,
                     get_hit_descriptions, get_hit_setups, get_hit_set_ids,
                     get_review, get_qualification_requirements,
                     get_hit_url, get_preview_url, get_aws_shell_list_hits)


# hard coded variables
EXPERIMENTER = 'rsw'
LANDING_FILE = 'index.html'

WORK_PATH = '/Volumes/turk/'
CONFIG_FILE = 'HIT.config'
TEST_SETUPS = dict(reward='0', max_assignments='1', assignment_duration_in_mins='60',
                   lifetime_in_hours='1', auto_approval_delay_in_hours='0')


def postHITs(project_name, account, host, save_log=False):
    """ The main function for posting hits to mturk
    Args:
        project_name(str): The name of the HIT to post.
        account(str): The requester account to use.
        host(str): The platform to send HITs.
        save_log(bool): Save a lot file or not.

    Returns:
        HITIds(list): A list of HITIDs of created HITS.
    """

    # make sure that project directory and files exist
    project_path = os.path.join(
        WORK_PATH, 'experiments', EXPERIMENTER, project_name)
    check_file_exists(project_path, LANDING_FILE)
    check_file_exists(project_path, CONFIG_FILE)

    if save_log:
        project_log_path = os.path.join(project_path, '.log')
        if not os.path.exists(project_log_path):
            os.mkdir(project_log_path)
        save_log_path = os.path.join(
            project_log_path, 'HITs_%s-%s.log' % (account, host))
        logger = set_logging_configs(__name__, save_log_path=save_log_path)
        logger.info(
            "\npost_hits(%s, %s, host='%s', save_log=%s)\n" % (project_name, account, host, save_log))
    else:
        logger = set_logging_configs(__name__)

    try:
        # read configuration settings
        config = read_config(project_path, CONFIG_FILE)

        # whether running a test
        if host == 'sandbox':
            test_mode = 1  # testing in https://workersandbox.mturk.com/
        elif config.has_section('TEST'):
            test_mode = 2  # testing in https://worker.mturk.com/
        else:
            test_mode = 0

        # description settings
        logger.info(get_review('description', config['INFO']))
        description_kwargs = get_hit_descriptions(config['INFO'])

        # setups settings
        if test_mode:
            config['SETUP'] = TEST_SETUPS
        logger.info(get_review('setup', config['SETUP']))
        setup_kwargs = get_hit_setups(config['SETUP'])

        if config.has_section('HITSET'):
            hit_set_ids = get_hit_set_ids(config['HITSET'])
            def hit_set_url_builder(x): return '?HSetId=' + str(x)
        else:
            hit_set_ids = list(range(0, 1))
            def hit_set_url_builder(x): return ''

        # qualification requirement settings
        if not test_mode:
            requirement_review = "\nSpecify any additional qualifications Workers must meet ...\n"
        else:
            environments = {1: 'SANDBOX', 2: 'FORMAL'}
            requirement_review = ('\nYou are testing in a %s environment.\n' % environments.get(test_mode) +
                                  'Qualification requirements are skipped')
            requirement_review += ' except for the testing qualification.\n\n' if test_mode == 2 else '.\n'

        requirement_kwarg_list = []
        # percent assignments approved
        if config.has_section('PERCENT APPROVED') and not test_mode:
            args = ('percent_assignments_approved', config['PERCENT APPROVED'])
            requirement_review += get_review(*args)
            requirement_kwarg_list.append(
                get_qualification_requirements(*args)
            )
            del args

        # num hit approved
        if config.has_section('NUM APPROVED') and not test_mode:
            args = ('num_hit_approved', config['NUM APPROVED'])
            requirement_review += get_review(*args)
            requirement_kwarg_list.append(
                get_qualification_requirements(*args)
            )
            del args

        # location (Country)
        if config.has_section('LOCATION') and not test_mode:
            args = ('location', config['LOCATION'])
            requirement_review += get_review(*args)
            requirement_kwarg_list.append(
                get_qualification_requirements(*args)
            )
            del args

    except Exception:
        logger.exception("\n!!! SOME ERRORS HAVE OCCURRED !!!\n\n")
    else:
        # Step 1: create a mturk client
        mtc = make_mtc(account, host)

        # exclude the participants who have completed a previous task
        if config.has_section('EXCLUDE QUALIFICATION TYPE') and not test_mode:
            args = ('exclude_qualification_type',
                    config['EXCLUDE QUALIFICATION TYPE'])
            requirement_review += get_review(*args, mtc=mtc)
            requirement_kwarg_list.append(
                get_qualification_requirements(*args)
            )

        # only include the participants who have a specific qualification type
        if config.has_section('INCLUDE QUALIFICATION TYPE') and not test_mode:
            args = ('include_qualification_type',
                    config['INCLUDE QUALIFICATION TYPE'])
            requirement_review += get_review(*args, mtc=mtc)
            requirement_kwarg_list.append(
                get_qualification_requirements(*args)
            )

        if test_mode == 2:
            args = ('include_qualification_type', config['TEST'])
            requirement_review += get_review(*args, mtc=mtc)
            requirement_kwarg_list = [
                get_qualification_requirements(*args)
            ]
        logger.info(requirement_review)

        # HIT info summary
        n_assignments = setup_kwargs['MaxAssignments']
        n_sets = len(hit_set_ids)
        n_workers = n_assignments * n_sets

        logger.info('\nHIT Summary\n' +
                    '  Name      : %s\n' % config["INFO"]["title"] +
                    '  Host      : %s %s\n' % (account, host) +
                    ('  HSetId    : %s \n' % ", ".join(map(str, hit_set_ids)) if n_sets > 1 else '') +
                    '  N Workers : %d = %d (assignment) * %d (set)\n' % (n_workers, n_assignments, n_sets))

        # check point: log the account balance and expenses if it is a formal testing
        if host == 'formal':
            account_balance = float(mtc.get_account_balance()[
                'AvailableBalance'])

            reward = float(setup_kwargs['Reward'])
            service_fee = reward * (0.2 if n_assignments < 10 else 0.4)
            total_cost = n_workers * (reward + service_fee)

            logger.info('\n%d participants @ $%.2f ($%.2f HIT + $%.2f service fee) = $%.2f\n' % (n_workers, reward + service_fee, reward, service_fee, total_cost) +
                        '\nAccount balance of %s %s\n' % (account, host) +
                        '  Before HIT : $%.2f\n' % account_balance +
                        '  After HIT  : $%.2f\n' % (account_balance - total_cost))

        # action required: check the above information and decide whether to proceed or not
        notice = '\nDo you want to proceed to publish %s for %s %s? [y/n]: ' % (project_name, account.upper(), host.upper())
        if not is_confirmed(notice):
            logger.info('\nThe task is cancelled, quiting now ...\n' +
                        '\n----------------------------------\n')
            return

        # Step 2: create new HITs
        HITIds = []
        for set_id in hit_set_ids:
            hit_url = get_hit_url(project_name, EXPERIMENTER,
                                  LANDING_FILE) + hit_set_url_builder(set_id)

            question = ExternalQuestion(external_url=hit_url).get_as_xml()
            new_hit = mtc.create_hit(Question=question,
                                     **description_kwargs, **setup_kwargs,
                                     QualificationRequirements=requirement_kwarg_list)

            HITId = new_hit["HIT"]["HITId"]
            HITGroupId = new_hit["HIT"]["HITGroupId"]
            HITIds.append(HITId)

        # preview url
        preview_url = get_preview_url(host)
        logger.info('\nNew HITs have been created. You can preview them here:\n' +
                    '%s?groupId=%s\n\n' % (preview_url, HITGroupId) +
                    'Here are the HITIDs:\n' + '\n'.join(HITIds) + '\n')

        # aws shell command
        list_hits_command = get_aws_shell_list_hits(
            HITGroupId, host, max_results=len(HITIds))
        logger.info('\nAWS CLI command for listing created HITs:\n\n' +
                    list_hits_command +
                    '\n\n=======================================\n')

        return HITIds


if __name__ == '__main__':
    import argparse

    # create parser object
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', type=str,
                        help='Which project to post?')
    parser.add_argument('--account', type=str,
                        help='Which requester account to use?')
    parser.add_argument('--host', type=str, default='sandbox',
                        help='Which platform to host, sandbox or formal?')
    parser.add_argument('--save_log', type=int, default=0,
                        help='Save a log file or not?')

    # parse terminal inputs
    args = parser.parse_args()

    # save the log if running actual mturk experiment
    save_log = True if args.host == 'formal' else args.save_log

    # post HIT to mturk
    postHITs(args.project, args.account, args.host, save_log=save_log)
