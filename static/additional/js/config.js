let sProvider = $("#cloud_storage").val();
storageProvider(sProvider);

$("#cloud_storage").change(function (e) {
  storageProvider($(this).val());
});

function storageProvider(storage) {
  $(`.form_section.${storage}`).show("slow");
  $(".form_section").not(`.${storage}`).hide("slow");
  $('[name="cloud_storage"]').val(storage);
}

function checkAuth(resp) {
  if (!resp.error) {
    $("#alert_google_auth").attr("class", "alert alert-success");
    $("#alert_google_auth").html(`<b>Authenticated</b>`);
  }
}
