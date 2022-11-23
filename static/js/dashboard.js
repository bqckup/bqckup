function dashboard() {
  return {
    bqckups: false,
    async backup_now() {
      let name = this.$el.getAttribute("backup-name");
      let request = await fetch(`backup/backup_now/${name}`);
      let response = await request.json();
      if (response.error) {
        return Swal.fire("Failed to backup", response.message, "error");
      }
      return Swal.fire("Success", response.message, "success");
    },
    init() {},
  };
}
