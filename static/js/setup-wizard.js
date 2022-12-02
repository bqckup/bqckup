function setupWizard() {
  return {
    keySetup: true,
    showFormConfig: false,
    key: null,
    configBackup: null,
    configStorage: null,
    clientIdKey: null,
    clientSecretKey: null,
    region: null,
    bucket: null,
    endpointURL: null,
    storageName: null,
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
      formData.append("key", this.key);
      formData.append("name", this.storageName);
      formData.append("config_bqckup", this.configBackup);
      formData.append("config_storage", this.configStorage);
      formData.append("client_id", this.clientIdKey);
      formData.append("client_secret", this.clientSecretKey);
      formData.append("region", this.region);
      formData.append("bucket", this.bucket);
      formData.append("endpoint_url", this.endpointURL);
      let request = await fetch("/setup/save", {
        method: "POST",
        body: formData,
      });
      if (request.status == 200) {
        return Swal.fire({
          icon: "success",
          title: "Success",
          text: "Successfully create",
          showConfirmButton: false,
        }).then(() => {
          window.location.href = "/";
        });
      }
      return Swal.fire({
        icon: "error",
        title: "Error",
        text: "Failed to create",
        showConfirmButton: false,
      }).then(() => {
        window.location.reload();
      });
    },

    init() {},
  };
}
