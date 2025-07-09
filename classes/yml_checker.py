from constant import BQ_PATH, STORAGE_CONFIG_PATH, SITE_CONFIG_PATH
from classes.file import File
from classes.yml_parser import Yml_Parser
from rich import print

class Yml_Checker:
    def checker():
        is_error = False

        # check if storage is exist
        if not File().is_exists(STORAGE_CONFIG_PATH):
            print ("\n [red]Storage config not found[/red]")
            is_error = True

        # storage check
        try:
            Yml_Parser.parse(STORAGE_CONFIG_PATH)
        except Exception as e:
            print ("\n [red]Error in storage config[/red] \n")
            is_error = True
        

        # site check
        files = File().get_file_list(SITE_CONFIG_PATH)
        files = [file for file in files if file.endswith('.yml')]
        
        for file in files:
            try:
                Yml_Parser.parse(file)
            except Exception as e:
                print(f" [red]Error in site config on[/red] {file} \n")
                is_error = True
        
        if is_error:
            sys.exit()

