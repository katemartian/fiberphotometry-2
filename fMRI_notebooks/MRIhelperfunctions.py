import subprocess
import os
import numpy as np
import pandas as pd

from os.path import expanduser
home = expanduser("~")

# Creates an empty class, to group a bunch of variables.
# See https://www.oreilly.com/library/view/python-cookbook/0596001673/ch01s08.html
# doesnt work with papermill! non json seriliazable error
class Settings:
    def __init__(self, **kwds):
        self.__dict__.update(kwds)




def runAFNI(inputstring):
    print(inputstring)
    subprocess.run(inputstring,shell=True, check=True)
    
    
def splitall(path):
    """
    splitall function from: https://www.safaribooksonline.com/library/view/python-cookbook/0596001673/ch04s16.html
    """
    allparts = []
    while 1:
        parts = os.path.split(path)
        if parts[0] == path:  # sentinel for absolute paths
            allparts.insert(0, parts[0])
            break
        elif parts[1] == path: # sentinel for relative paths
            allparts.insert(0, parts[1])
            break
        else:
            path = parts[0]
            allparts.insert(0, parts[1])
    return allparts


def walklevel(some_dir, level=1):
    """
    works just like os_walk but one can specify how many levels it will go in directory tree
    from: https://stackoverflow.com/questions/229186/os-walk-without-digging-into-directories-below
    """
    some_dir = some_dir.rstrip(os.path.sep)
    assert os.path.isdir(some_dir)
    num_sep = some_dir.count(os.path.sep)
    for root, dirs, files in os.walk(some_dir):
        yield root, dirs, files
        num_sep_this = root.count(os.path.sep)
        if num_sep + level <= num_sep_this:
            del dirs[:]


def find_animal_folders(info, raw_folder):        
    for animal in info.columns:
        for folderName, subfolders, filenames in walklevel(raw_folder, 1):
            for file in filenames:
                if (file == 'subject' and 'Pilot data' not in folderName):
                    if animal in open(os.path.join(folderName,file)).read().lower():
                        info.loc['folder', animal] = folderName
    return info

def getinfo(folders):
    info = pd.read_excel(f"{folders['main']}/{folders['excel']}", convert_float=True)
    info.columns = map(str.lower, info.columns)
    info.set_index('scan', inplace=True)
    # info = info.append({'animal-id': 'folder'}, ignore_index=True)

    # def get_subject_folders(main_folder, info):
    #     for animal in info.columns

    info = find_animal_folders(info, folders['raw'])
    return(info)


def convertAll(folder_in, folder_out):
    """
    requires original paravision folder structure with subject file.
    requires Bru2 from github in PATH
    converts all 2dseqs, except tripilots, with original dimensions as .nii to folder_out
    """
    runAFNI(f'Bru2 -a -o {folder_out} {folder_in}/subject')
    
    

def check_and_convert(folders, animal):
    """
    Is there already a folder for this animal in the main analysis folder?
    If not, create it and convert all 2dseqs of this animal and move them to analysis subfolder
    """
    animal_output_folder = os.path.join(folders['analysis'],animal)
    if not os.path.exists(animal_output_folder):
        os.makedirs(animal_output_folder)
        convertAll(folders['animal'], animal_output_folder)

        
        
def simple_coreg(template, scanA, scanB, out_dir):
    """
    scanA will be coregistered to template, identical transformation will be applied to scanB (no motion between A and B!)
    """
    parameters = os.path.join(out_dir,'1dparams.1D')
    scanAloc = f"{out_dir}/A_coreg.nii"
    scanBloc = f"{out_dir}/B_coreg.nii"
    runAFNI(f"3dAllineate -base {template} -source {scanA} -prefix {scanAloc} -cost ls -zclip -interp quintic -final wsinc5 -twopass -twoblur 2 -fineblur 0.5 -nmatch 80% -conv 0.01 -1Dparam_save {parameters}")
    runAFNI(f"3dAllineate -1Dparam_apply {parameters} -source {scanB} -prefix {scanBloc} -cost ls -zclip -interp quintic -final wsinc5 -twopass -twoblur 2 -fineblur 0.5 -nmatch 80% -conv 0.01 -master {template}")
    
    return scanAloc, scanBloc
    

def coreg_epi(template, scanA, scanB, out_dir):
    """
    difference to simple_coreg: also does -tshift,
    volreg off as global bolus inflow could be mistaken for movement.
    WARNING: AFNI gives error for some reason
    """
    runAFNI("python2.7 " + home + "/abin/align_epi_anat.py -dset1to2 -dset1 " + scanA + " -dset2 " + template + \
                                " -child_dset1 " + scanB + \
                                " -output_dir " + out_dir + \
                                " -dset1_strip None -dset2_strip None" \
                                " -overwrite" \
                                " -big_move" \
                                " -volreg off" \
                                " -Allineate_opts '-maxrot 10 -maxshf 3 -conv 0.005 -twofirst -twoblur 0.8 -source_automask+2 -final wsinc5'" \
                                " -tshift on -tshift_opts '-tzero 0 -quintic'" \
                                " -suffix .coreg" \
                                " -save_vr" \
                                " -cost ls")

