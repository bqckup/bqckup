function backupDetail() {
  return {
    async downloadFile(fileName) {
      let formData = new FormData();
      formData.append("fileName", fileName);
      let request = await fetch(
        "/api/backup/get_download_link/",
        { method: "POST" },
        {
          body: formData,
        }
      );
      let response = await request.json();
      if (response.error) {
        return Swal.fire("Error", response.message, "error");
      }
      window.location.href = response.url;
    },
    init() {
      alert("Init");
    },
  };
}
