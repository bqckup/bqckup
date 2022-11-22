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
      this.payload.options.storage = this.storages[0];
    },
    open(step = false) {
      this.step = this.step == "files" ? "database" : "options";
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
              name: "Setup options",
              description: "Setup your bqckup options",
            };
    },
    previous() {
      let previousStep = this.step == "options" ? "database" : "files";
      this.open(previousStep);
    },
    next() {
      var invalidChars = /[ `!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?~]/;
      switch (this.step) {
        case "files":
          if (invalidChars.test(this.payload.backup.name)) {
            return Swal.fire(
              "Backup name is invalid",
              "Backup name must not contains space or symbols",
              "error"
            );
          }
          if (!this.$refs.form_files.checkValidity()) {
            return Swal.fire(
              "Empty Data",
              "The form needs to be filled in to proceed to the next step",
              "error"
            );
          }
      }
      this.open();
    },
    async testDatabaseConnection() {
      if (!this.$refs.form_files.checkValidity()) {
        return Swal.fire("Empty Data", "Form data can not be empty", "error");
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
        return Swal.fire("Process Failed", response.message, "error");
      }
      this.notifications.testingDatabaseFailed = false;
      this.notifications.testingDatabaseSuccess = true;
      this.$el.disabled = false;
    },
    payload: {
      backup: {
        name: "backupname",
        path: "example_path",
      },
      database: {
        host: "localhost",
        type: "mysqli",
        name: "mysql",
        user: "root_db",
        password: "coklatmanis",
      },
      options: {
        storage: "",
        interval: "daily",
        retention: "7",
        save_locally: "no",
        notification_email: "",
      },
    },
    async submit() {
      this.$refs.buttonSave.disabled = true;
      let formData = new FormData();
      for (const _p in this.payload) {
        if (_p == "options") {
          this.payload[_p].save_locally =
            this.payload[_p].save_locally === true ? "yes" : "no";
          if (this.payload[_p].notification_email == "") {
            delete this.payload[_p].notification_email;
          }
        }
        let dataEachStep = JSON.stringify(this.payload[_p]);
        formData.append(_p, dataEachStep);
      }
      let request = await fetch("/backup/save", {
        method: "POST",
        body: formData,
      });
      if (request.status != 200) {
        console.error(request);
        return Swal.fire(
          "Process Failed",
          "Failed to create bqckup, check console",
          "error"
        );
      }
      let response = await request.json();
      this.$refs.buttonSave.disabled = false;
      return Swal.fire({
        icon: "success",
        title: "Success",
        text: "Successfully create",
        showConfirmButton: false,
      }).then(() => {
        window.location.href = "/";
      });
    },
  };
}
