import yaml

with open("sample.yml", "r") as stream:
    try:
        x = yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        print(exc)
    finally:
        stream.close()

for xx in x['storages']:
    print(xx)
