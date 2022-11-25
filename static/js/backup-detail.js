function backupDetail() {
  return {
    async downloadFile(fileName, storageName) {
      let formData = new FormData();
      formData.append("file_name", fileName);
      formData.append("storage_name", storageName);
      let request = await fetch("/backup/get_download_link", {
        method: "POST",
        body: formData,
      });
      let response = await request.json();
      if (response.error) {
        return Swal.fire("Error", response.message, "error");
      }
      window.location.href = response.url;
    },
    init() {},
  };
}
