import yaml
# print(yaml.safe_load("""
# Bqckup:
#   name: First Backup
#   path:
#     - /home/thisnugroho.my.id
#   database:
#     username: root_db
#     password: coklatmanis
#     database_name: database
#   config:
#     schedule: daily
#     email: this.nugroho@gmail.com #for notification
#     time: 00:00
#     retention: 7
#     keep_files: true
#     """))
class MyDumper(yaml.Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super(MyDumper, self).increase_indent(flow, False)
        
document = {
    "bqckup": {
        "name": "First backup",
        "path": ["/home/thisnugroho.my.id", "/home/thisnugroho.my.id/nginx"],
        "database": {
            "username": "root_db",
            "password": "coklatmanis",
            "database_name": "database"
        },
        "config": {
            "schedule": "daily",
            "email": "this.nugroho@gmail.com",
            "time": "00:00",
            "retention": 7,
            "keep_files": True
        }
    }
}
me = yaml.dump(document, Dumper=MyDumper, sort_keys=False, default_flow_style=False)
print(me)
