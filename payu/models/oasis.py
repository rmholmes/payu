# coding: utf-8
"""
The payu interface for the OASIS coupler
-------------------------------------------------------------------------------
Contact: Marshall Ward <marshall.ward@anu.edu.au>
-------------------------------------------------------------------------------
Distributed as part of Payu, Copyright 2011 Marshall Ward
Licensed under the Apache License, Version 2.0
http://www.apache.org/licenses/LICENSE-2.0
"""

# Standard Library
import os
import sys
import shlex
import shutil
import subprocess

# Extensions
import f90nml

# Local
from payu.fsops import mkdir_p, make_symlink
from payu.models.model import Model
from payu.namcouple import Namcouple

class Oasis(Model):

    #---
    def __init__(self, expt, name, config):
        super(Oasis, self).__init__(expt, name, config)

        self.model_type = 'oasis'
        self.copy_restarts = True
        self.copy_inputs = True

        self.config_files = ['namcouple']


    def setup(self):
        super(Oasis, self).setup()

        # Copy OASIS data to the other submodels

        # TODO: Parse namecouple to determine filelist
        # TODO: Let users map files to models
        input_files = [f for f in os.listdir(self.work_path)
                       if not f in self.config_files]

        for model in self.expt.models:

            # Skip the oasis self-reference
            if model == self:
                continue

            mkdir_p(model.work_path)
            for f_name in (self.config_files + input_files):
                f_path = os.path.join(self.work_path, f_name)
                f_sympath = os.path.join(model.work_path, f_name)
                make_symlink(f_path, f_sympath)


    def set_timestep(self, t_step):

        namcpl_path = os.path.join(self.work_path, 'namcouple')
        namcpl = Namcouple(namcpl_path, 'access')
        namcpl.set_ice_ocean_coupling_timestep(str(t_step))
        namcpl.write()

        for model in self.expt.models:

            if model.model_type == 'cice':

                # Set namcouple timesteps

                ice_ts = model.config.get('timestep')
                if ice_ts:
                    model.set_oasis_timestep(ice_ts)

                # Set ACCESS coupler timesteps

                input_ice_path = os.path.join(model.work_path, 'input_ice.nml')
                input_ice = f90nml.read(input_ice_path)

                input_ice['coupling_nml']['dt_cpl_io'] = t_step

                input_ice.write(input_ice_path, force=True)

            elif model.model_type == 'matm':

                input_atm_path = os.path.join(model.work_path, 'input_atm.nml')
                input_atm = f90nml.read(input_atm_path)

                input_atm['coupling']['dt_atm'] = t_step

                input_atm.write(input_atm_path, force=True)

            elif model.model_type == 'mom':

                input_nml_path = os.path.join(model.work_path, 'input.nml')
                input_nml = f90nml.read(input_nml_path)

                input_nml['auscom_ice_nml']['dt_cpl'] = t_step
                input_nml['ocean_solo_nml']['dt_cpld'] = t_step

                input_nml.write(input_nml_path, force=True)


    #---
    def archive(self):

        # TODO: Determine the exchange files
        restart_files = ['a2i.nc', 'i2a.nc', 'i2o.nc', 'o2i.nc']

        mkdir_p(self.restart_path)
        for f in restart_files:
            f_src = os.path.join(self.work_path, f)
            f_dst = os.path.join(self.restart_path, f)

            if os.path.exists(f_src):
                shutil.move(f_src, f_dst)

    #---
    def collate(self):
        pass
