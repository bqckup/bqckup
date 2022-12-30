function setupWizard() {
  return {
    keySetup: true,
    showFormConfig: false,
    key: null,
    clientIdKey: null,
    clientSecretKey: null,
    region: null,
    bucket: null,
    endpointURL: null,
    storageName: null,
    skip: false,
    next() {
      if (this.keySetup) {
        if (!this.key) {
          return alert("Please enter a key");
        }
        this.keySetup = false;
        return;
      }
      this.submit();
    },
    async submit() {
      let formData = new FormData();
      if (!this.key) {
        return Swal.fire(
          "Empty Data",
          "Please enter a key to continue",
          "error"
        );
      }
      // Validate storage name
      if (/\s/g.test(this.storageName)) {
        return Swal.fire(
          "Empty Data",
          "Storage name can not contains space",
          "error"
        );
      }
      formData.append("key", this.key);
      formData.append("name", this.storageName);
      formData.append("config_bqckup", this.$refs.configBackup.files[0]);
      formData.append("config_storage", this.$refs.configStorage.files[0]);
      formData.append("client_id", this.clientIdKey);
      formData.append("client_secret", this.clientSecretKey);
      formData.append("region", this.region);
      formData.append("bucket", this.bucket);
      formData.append("endpoint_url", this.endpointURL);
      formData.append("skip", this.skip);
      let request = await fetch("/setup/save", {
        method: "POST",
        body: formData,
      });
      let response = await request.json();
      if (request.status == 200) {
        return Swal.fire({
          icon: "success",
          title: "Success",
          text: response.message,
          showConfirmButton: false,
        }).then(() => {
          window.location.href = "/";
        });
      }
      return Swal.fire(
        response.message,
        "Check your data and try again",
        "error"
      );
    },

    init() {},
  };
}
