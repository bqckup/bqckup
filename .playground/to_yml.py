import yaml

x = {"name": "Dede Nugroho", "options": {"Gender": "Boys"}}

xx = yaml.dump(x, default_flow_style=False)
print(xx)
