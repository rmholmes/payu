# coding: utf-8

from payu import reversion
reversion.repython('2.7.6', __file__)

# Standard Library
import argparse
import errno
import importlib
import os
import pkgutil
import shlex
import socket
from string import digits
import subprocess
import sys

# Extensions
import yaml

# Local
from modelindex import index as supported_models
import subcommands

# Default configuration
default_config_filename = 'config.yaml'

#---
def parse():

    # Build the list of subcommand modules
    modnames = [mod for (_, mod, _)
                in pkgutil.iter_modules(subcommands.__path__,
                                        prefix=subcommands.__name__ + '.')
                if mod.endswith('_cmd')]

    subcmds = [importlib.import_module(mod) for mod in modnames]

    # Construct the subcommand parser
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()

    for cmd in subcmds:
        cmd_parser = subparsers.add_parser(cmd.title, **cmd.parameters)
        cmd_parser.set_defaults(run_cmd=cmd.runcmd)

        for arg in cmd.arguments:
            cmd_parser.add_argument(*arg['flags'], **arg['parameters'])

    # Display help if no arguments are provided
    if len(sys.argv) == 1:
        parser.print_help()
    else:
        args = vars(parser.parse_args())
        run_cmd = args.pop('run_cmd')
        run_cmd(**args)


#---
def get_config(config_path):

    if not config_path and os.path.isfile(default_config_filename):
        config_path = default_config_filename
 
    try:
        with open(config_path, 'r') as config_file:
            config = yaml.load(config_file)
    except (TypeError, IOError) as exc:
        if config_path == None:
            config = {}
        elif type(exc) == IOError and exc.errno == errno.ENOENT:
            print('payu: error: Configuration file {} not found.'
                  ''.format(config_path))
            sys.exit(errno.ENOENT)
        else:
            raise

    return config


#---
def get_model_type(model_type, config):

    # If no model type is given, then check the config file
    if not model_type:
        model_type = config.get('model')

    # If there is still no model type, try the parent directory
    if not model_type:
        model_type = os.path.basename(os.path.abspath(os.pardir))
        print('payu: warning: Assuming model is {} based on parent directory '
              'name.'.format(model_type))

    if not model_type in supported_models:
        print('payu: error: Unknown model {}'.format(model_type))
        sys.exit(-1)


#---
def get_env_vars(init_run=None, n_runs=None):

    payu_modname = next(mod for mod in os.environ['LOADEDMODULES'].split(':')
                        if mod.startswith('payu'))
    payu_modpath = next(mod for mod in os.environ['_LMFILES_'].split(':')
                        if payu_modname in mod).rstrip(payu_modname)

    payu_env_vars = {'PYTHONPATH': os.environ['PYTHONPATH'],
                     'PAYU_MODULENAME': payu_modname,
                     'PAYU_MODULEPATH': payu_modpath,
                    }

    if init_run:
        init_run = int(init_run)
        assert init_run >= 0

        payu_env_vars['PAYU_CURRENT_RUN'] = init_run

    if n_runs:
        n_runs = int(n_runs)
        assert n_runs > 0

        payu_env_vars['PAYU_N_RUNS'] = n_runs

    return payu_env_vars


#---
def submit_job(pbs_script, pbs_config, pbs_vars=None):

    hostname = socket.gethostname().rstrip(digits)

    pbs_qsub = 'qsub'
    pbs_flags = []

    pbs_queue = pbs_config.get('queue', 'normal')
    pbs_flags.append('-q {}'.format(pbs_queue))

    # Raijin doesn't read $PROJECT, which is required at login
    pbs_project = pbs_config.get('project', os.environ['PROJECT'])
    pbs_flags.append('-P {}'.format(pbs_project))

    pbs_walltime = pbs_config.get('walltime')
    if pbs_walltime:
        pbs_flags.append('-l walltime={}'.format(pbs_walltime))

    pbs_ncpus = pbs_config.get('ncpus')
    if pbs_ncpus:
        pbs_flags.append('-l ncpus={}'.format(pbs_ncpus))

    pbs_mem = pbs_config.get('mem')
    if pbs_mem:
        mem_rname = 'vmem' if hostname == 'vayu' else 'mem'
        pbs_flags.append('-l {}={}'.format(mem_rname, pbs_mem))

    pbs_jobname = pbs_config.get('jobname')
    if pbs_jobname:
        # TODO: Only truncate when using PBSPro
        pbs_jobname = pbs_jobname[:15]
        pbs_flags.append('-N {}'.format(pbs_jobname))

    pbs_priority = pbs_config.get('priority')
    if pbs_priority:
        pbs_flags.append('-p {}'.format(pbs_priority))

    pbs_wd = '-wd' if hostname == 'vayu' else '-l wd'
    pbs_flags.append(pbs_wd)

    # TODO: Make this optional
    pbs_flags.append('-j oe')

    if pbs_vars:
        pbs_vstring = ','.join('{}={}'.format(k, v)
                               for k, v in pbs_vars.iteritems())
        pbs_flags.append('-v ' + pbs_vstring)

    # Append any additional qsub flags here
    pbs_flags_extend = pbs_config.get('qsub_flags')
    if pbs_flags_extend:
        pbs_flags.append(pbs_flags_extend)

    # Collect flags
    pbs_flags = ' '.join(pbs_flags)

    # Construct full command
    cmd = '{} {} {}'.format(pbs_qsub, pbs_flags, pbs_script)

    try:
        subprocess.call(shlex.split(cmd))
    except subprocess.CalledProcessError as exc:
        print('payu: error: qsub submission error {}'.format(exc.errno))
        raise