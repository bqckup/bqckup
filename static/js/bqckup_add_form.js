function bqckup_add() {
  return {
    step: "files",
    form: {
      name: "Setup Files",
      description: "Setup your files",
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
      this.open();
    },
    testDatabaseConnection() {
      console.log(this.payload);
    },
    payload: {
      backup: {
        name: "",
        path: "",
      },
      database: {
        type: "",
        name: "",
        user: "",
        password: "",
      },
      configuration: {
        schedule: "",
      },
    },
    submit() {},
  };
}
