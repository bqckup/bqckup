var baseUrl = window.location.origin;

$(document).on("click", ".get_link_download", function (e) {
  let key = $(this).attr("key");
  getAndCopyDownloadUrl(key);
});

$(document).on("click", ".download_file", function (e) {
  let key = $(this).attr("key");
  downloadFile(key);
});

$("#skip_form_database").click(function (e) {
  moveToConfigForm();
});

$(document).on("click", ".backup_now", function (e) {
  e.preventDefault();
  let backupName = $(this).data("backup_name");
  $("#backup_loading_backup_name").text(backupName);
  $(this).addClass("disabled");

  let token = $(this).attr("token"),
    url = $(this).attr("href") + "?token=" + token;
  $("#backup_loading").fadeIn();
  $.get(url, (resp) => {
    if (!resp.error) {
      $(this).removeClass("disabled");
      successNotification("On Progress");
      getListBackup();
      getLastBackup();
      getLogBackup();
    } else {
      swalError(resp.msg);
    }
    $("#backup_done").fadeIn();
    $("#backup_loading").fadeOut();
  });
});

$(document).on("click", ".get_files", function (e) {
  $("#list_backup").modal("show");
  $("#listFiles").html(skeleton);
  let token = $(this).attr("token");
  $.get(`${baseUrl}/list_files?token=${token}`, (resp) => {
    $("#listFiles").html(resp);
  });
});

$(document).on("click", ".backup_edit", function (e) {
  let token = $(this).attr("token");
  $.get(`${baseUrl}/get_backup_detail?token=${token}`, (data) => {
    if (data.error) {
      console.log("Error caught");
      return;
    }
    let config = data.config,
      database = data.database,
      folder = data.folder,
      formConfig = $("#form_config").find("form"),
      formFolder = $("#form_folder").find("form"),
      formDatabase = $("#form_database").find("form");

    $('[name="backup_id"]').val(folder.id);
    $.each(folder, (key, val) => {
      formFolder.find(`[name="${key}"]`).val(val);
    });

    $.each(database, (key, d) => {
      formDatabase.find(`[name="${key}"]`).val(d);
    });

    $.each(config, (key, c) => {
      let dom = formConfig.find(`[name="${c.name}"]`);
      switch (dom.prop("type")) {
        case "checkbox":
          if (c.value) {
            dom.attr("checked", true);
          }
          break;
        case "radio":
          if (dom.val() == c.value) {
            dom.attr("checked");
          }
          break;
        default:
          dom.val(c.value);
          break;
      }
    });
    $("#add_backup").modal("show");
  });
});

async function updateNow(button) {
  $(button).addClass("disabled");
  let spinner = `<span class="spinner-border spinner-border-sm mr-2" role="status"></span>Updating...`,
    svgCheck = `
    <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-check" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
    <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
    <path d="M5 12l5 5l10 -10"></path>
    </svg>`;

  $(button).html(spinner);

  let response = await updateData();

  if (response.status) {
    $(button).css("outline", "0 !important");
    $(button).removeClass("disabled");
    $(button).css("color", "green");
    $(button).blur();
    $(button).html(svgCheck + "Update Success");
  }
}

function updateData() {
  return new Promise((resolve, reject) => {
    $.get(`${baseUrl}/do_update`, (response) => {
      resolve(response);
    });
  });
}

function refreshPage() {
  window.location.reload();
}

function moveToConfigForm(resp = false) {
  $("[href='#form_config']").tab("show");
}

function moveToDatabaseForm(resp) {
  /* refresh list backup */
  getListBackup();

  $("[name='backup_id']").each(function (e) {
    let backup_id = resp.backup_id;
    $(this).val(backup_id);
  });
  $("[href='#form_database']").tab("show");
}

function downloadFile(key) {
  $.get(`${baseUrl}/get_link_download?key=${key}`, (resp) => {
    window.location = resp.url;
  });
}

function getAndCopyDownloadUrl(key) {
  $.get(`${baseUrl}/get_link_download?key=${key}`, (resp) => {
    let url = resp.url;
    $("#give_me_the_link").val(url);
    $("#show_link_modal").modal("show");
  });
}

document.getElementById("button_copy").addEventListener("click", function () {
  copyToClipboard(document.getElementById("give_me_the_link"));
});

function copyToClipboard(elem) {
  // create hidden text element, if it doesn't already exist
  var targetId = "_hiddenCopyText_",
    isInput = elem.tagName === "INPUT" || elem.tagName === "TEXTAREA",
    origSelectionStart,
    origSelectionEnd;

  if (isInput) {
    // can just use the original source element for the selection and copy
    target = elem;
    origSelectionStart = elem.selectionStart;
    origSelectionEnd = elem.selectionEnd;
  } else {
    // must use a temporary form element for the selection and copy
    target = document.getElementById(targetId);
    if (!target) {
      var target = document.createElement("textarea");
      target.style.position = "absolute";
      target.style.left = "-9999px";
      target.style.top = "0";
      target.id = targetId;
      document.body.appendChild(target);
    }
    target.textContent = elem.textContent;
  }
  // select the content
  var currentFocus = document.activeElement;
  target.focus();
  target.setSelectionRange(0, target.value.length);

  // copy the selection
  var succeed;
  try {
    succeed = document.execCommand("copy");
  } catch (e) {
    succeed = false;
  }
  // restore original focus
  if (currentFocus && typeof currentFocus.focus === "function") {
    currentFocus.focus();
  }

  if (isInput) {
    // restore prior selection
    elem.setSelectionRange(origSelectionStart, origSelectionEnd);
  } else {
    // clear temporary content
    target.textContent = "";
  }
  if (succeed) {
    $("#copy_success").fadeIn();
  }
}

function getLogBackup() {
  $("#log_ajax").html(skeleton);
  let url = `${baseUrl}/get_list_logs`;
  $.get(url, (response) => {
    $("#log_ajax").html(response);
  });
}

function getLastBackup() {
  $("#last_backup_ajax").html(skeleton);
  let url = `${baseUrl}/get_last_backup`;
  $.get(url, (response) => {
    $("#last_backup_ajax").html(response);
  });
}

function getListBackup() {
  $("#list_backup_ajax").html(skeleton);
  let url = `${baseUrl}/get_list_backup`;
  $.get(url, (response) => {
    $("#list_backup_ajax").html(response);
  });
}

$(document).ready(function (e) {
  getListBackup();
  getLastBackup();
  getLogBackup();
});
