function bqckup_add() {
  return {
    storages: [],
    step: "files",
    form: {
      name: "Setup Files",
      description: "Setup your files",
    },
    notifications: {
      testingDatabaseSuccess: false,
      testingDatabaseFailed: false,
    },
    init() {
      this.fetchStorages();
    },
    async fetchStorages() {
      let request = await fetch("/backup/get_storages");
      if (request.status != 200) {
        return alert("Failed to fetching storages");
      }
      let response = await request.json();
      this.storages = response;
    },
    open(step = false) {
      this.step = this.step == "files" ? "database" : "configuration";
      if (step) {
        this.step = step;
      }
      this.form =
        this.step == "database"
          ? {
              name: "Setup Database",
              description: "Setup your database",
            }
          : {
              name: "Setup configuration",
              description: "Setup your configuration",
            };
    },
    previous() {
      let previousStep = this.step == "configuration" ? "database" : "files";
      this.open(previousStep);
    },
    next() {
      switch (this.step) {
        case "files":
          if (!this.$refs.form_files.checkValidity()) {
            return alert(
              "The form needs to be filled in to proceed to the next step"
            );
          }
      }
      this.open();
    },
    async testDatabaseConnection() {
      if (!this.$refs.form_files.checkValidity()) {
        return;
      }
      this.$el.disabled = true;
      let formData = new FormData();
      for (const _data in this.payload.database) {
        formData.append(_data, this.payload.database[_data]);
      }
      let request = await fetch("/backup/test_db_connection", {
        method: "POST",
        body: formData,
      });
      let respose = await request.json();
      if (respose.error) {
        this.notifications.testingDatabaseFailed = true;
        console.error(respose.message);
        this.$el.disabled = false;
        return;
      }
      this.notifications.testingDatabaseFailed = false;
      this.notifications.testingDatabaseSuccess = true;
      this.$el.disabled = false;
    },
    payload: {
      backup: {
        name: "example_name",
        path: "example_path",
      },
      database: {
        host: "localhost",
        type: "mysqli",
        name: "mysql",
        user: "root_db",
        password: "coklatmanis",
      },
      configuration: {
        schedule: "",
      },
    },
    submit() {},
  };
}
