function dashboard() {
  return {
    bqckups: false,
    async fetchBqckups() {
      let request = await fetch("/backup/list");
      let response = await request.json();
      if (request.status >= 500) {
        return alert("Failed to fetch backup, please check logs");
      }
      this.bqckups = response;
    },
    async init() {
      this.fetchBqckups();
    },
  };
}
