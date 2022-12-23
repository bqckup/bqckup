var skeleton = `<ul class="list-group list-group-flush">
<li class="list-group-item">
  <div class="row align-items-center">
    <div class="col-auto">
      <div class="skeleton-avatar"></div>
    </div>
    <div class="col-7">
      <div class="skeleton-line"></div>
      <div class="skeleton-line"></div>
    </div>
    <div class="col-2 ms-auto text-end">
      <div class="skeleton-line"></div>
      <div class="skeleton-line"></div>
    </div>
  </div>
</li>
<li class="list-group-item">
  <div class="row align-items-center">
    <div class="col-auto">
      <div class="skeleton-avatar"></div>
    </div>
    <div class="col-7">
      <div class="skeleton-line"></div>
      <div class="skeleton-line"></div>
    </div>
    <div class="col-2 ms-auto text-end">
      <div class="skeleton-line"></div>
      <div class="skeleton-line"></div>
    </div>
  </div>
</li>
<li class="list-group-item">
  <div class="row align-items-center">
    <div class="col-auto">
      <div class="skeleton-avatar"></div>
    </div>
    <div class="col-7">
      <div class="skeleton-line"></div>
      <div class="skeleton-line"></div>
    </div>
    <div class="col-2 ms-auto text-end">
      <div class="skeleton-line"></div>
      <div class="skeleton-line"></div>
    </div>
  </div>
</li>
<li class="list-group-item">
  <div class="row align-items-center">
    <div class="col-auto">
      <div class="skeleton-avatar"></div>
    </div>
    <div class="col-7">
      <div class="skeleton-line"></div>
      <div class="skeleton-line"></div>
    </div>
    <div class="col-2 ms-auto text-end">
      <div class="skeleton-line"></div>
      <div class="skeleton-line"></div>
    </div>
  </div>
</li>
</ul>`;

var ajax_options = {
  error: ajaxError,
  success: ajaxResponse,
  dataType: "json",
  beforeSubmit: showPostLoading,
};

$(".time_picker").flatpickr({
  enableTime: true,
  noCalendar: true,
  dateFormat: "H:i",
  time_24hr: false,
  defaultDate: "00:00",
});

var swalToast = Swal.mixin({
  toast: true,
  position: "top-end",
  showConfirmButton: false,
  timer: 3000,
  timerProgressBar: true,
  didOpen: (toast) => {
    toast.addEventListener("mouseenter", Swal.stopTimer);
    toast.addEventListener("mouseleave", Swal.resumeTimer);
  },
});

var ajaxErrorCount = 0;

$(".form_ajax, .ajax_form").each(function (e) {
  $(this).on("submit", function (e) {
    e.preventDefault();
    $(this).ajaxSubmit(ajax_options);
  });
});

$(document).on("click", ".delete_confirm", function (e) {
  e.preventDefault();

  let id = $(this).attr("data-id") || $(this).attr("token"),
    url = $(this).attr("href") || $(this).attr("url"),
    callback = $(this).attr("callback"),
    elRemove = callback == "remove_tr" ? $(this).closest("tr") : false;

  deleteConfirm(url, id, elRemove, callback);
});

function buttonLoading(button, enabled = true, text = "Save") {
  if (!button.length) return;
  if (enabled) {
    button.removeAttr("disabled");
    button.html(text);
  } else {
    button.attr("disabled", true);
    button.html(
      `<span class="spinner-border spinner-border-sm mr-2" role="status"></span>
      Loading`
    );
  }
}

function swalSuccessResponse(msg = false, url = false) {
  msg = msg ? msg : "Data processed";
  url = !url || url === typeof undefined ? false : url;

  Swal.fire({
    title: msg,
    text: "Thank you",
    icon: "success",
    timer: 1000,
    showConfirmButton: false,
    onClose: function () {
      if (url) window.location = url;
    },
  }).then(
    function () {},
    // handling the promise rejection
    function (dismiss) {
      if (dismiss === "timer" && url) {
        window.location = url;
      }
    }
  );
}

function swalError(msg, scroll = true) {
  Swal.fire({
    title: "Error ",
    text: msg,
    icon: "warning",
    confirmButtonColor: "#E23B4F",
    confirmButtonText: "Ok",
  }).then(function () {
    if (scroll === true) {
      $("html, body").animate(
        {
          scrollTop: 0,
        },
        "slow"
      );
    } else {
      $(scroll).scrollTo(400);
    }
  });

  return;
}

function checkRequiredInput(form) {
  return form.validate();
}

function showPostLoading(elem, form) {
  var button = form.find('button[type="submit"]');
  buttonLoading(button, false);

  var isFormComplete = checkRequiredInput(form);

  if (!isFormComplete) {
    swalError("Mohon lengkapi isian form", "input.is-invalid");
    return false;
  }

  //is there any input confirm type, if so make sure it same as confirm input
  if ($(form).find(".input_confirm").length) {
    var input = $(form).find(".input");
    var input_confirm = $(form).find(".input_confirm");
    if (input.val() != input_confirm.val()) {
      var msg = input.attr("msg")
        ? input.attr("msg")
        : "Pastikan input konfirmasi sesuai";
      errorNotification(msg, 6000);

      input_confirm.css("border-color", "red");
      input_confirm.val("");
      input_confirm.focus();
      return false;
    }
  }

  $(form).removeAttr("enctype");
  //end removing element
}

function clearFormInput(form) {
  form = form.length ? form : $(form);

  form.find("input").not(".static, .nochange, .noChange").val("");
  form.find("select").not(".static, .nochange, .noChange").val("");
  form.find("radio").not(".static, .nochange, .noChange").val("");
  form.find("textarea").not(".static, .nochange, .noChange").val("");
  form
    .find(".select2")
    .not(".static, .nochange, .noChange")
    .val("")
    .trigger("change");
  form
    .find("select")
    .not(".static, .nochange, .noChange")
    .val("")
    .trigger("change");

  //clear the upload preview
  form.find(".image_preview ").html("");
  form.find(".upload_keterangan").attr("style", "");
  form.find(".uploadbutton").attr("style", "");
}

function ajaxResponse(responseText, statusText, xhr, form) {
  let msg = responseText.msg ? responseText.msg : "Error while processing data";

  if (form) {
    var button = form.find('button[type="submit"]');
  }

  if (responseText.error == 1) {
    errorNotification(msg);
    buttonLoading(button, true);
  }

  if (responseText.error == 0) {
    let msg = responseText.msg
      ? responseText.msg
      : "Data successfully processed";

    if (responseText.redirect === undefined) {
      successNotification(responseText.msg);
    } else {
      swalSuccessResponse(msg, responseText.redirect);
    }

    let isModalForm = $(form).closest(".modal").length,
      preventModalClose = $(form).attr("prevent-close");

    if (isModalForm && !preventModalClose) {
      let id = $(form).closest(".modal").attr("id");
      $("#" + id).modal("hide");
    }

    let clearform = $(form).attr("clearform");
    clearform = clearform ? clearform : $(form).attr("clearForm");
    if (typeof clearform !== "undefined" && clearform !== false) {
      clearFormInput(form);
    }

    let generateToken = $(form).attr("generatetoken");
    generateToken = generateToken
      ? generateToken
      : $(form).attr("generateToken");
    if (typeof generateToken !== "undefined" && generateToken !== false) {
      let new_token = generate_token();

      $(form).find('input[name="form_token"]').val(new_token);
      $(form).find('input[name="token"]').val(new_token);
      $(form).find(".single_uploader ").attr("data-token", new_token);
    }
    // pass to callback
    if (form) {
      buttonLoading(button, true);
    }
    runCallBack(form, responseText);
  }
}

function runCallBack(el, resp, callback = false) {
  var callBackExist = callback ? callback : $(el).attr("callback");
  console.log(callBackExist);

  if (typeof callBackExist !== typeof undefined && callBackExist !== false) {
    console.info("Callback called " + callBackExist);
    window[callBackExist](resp);
  }
}

function ajaxError(responseText, statusText, xhr, form) {
  ajaxErrorCount++;
  if (ajaxErrorCount > 2) {
    errorNotification("Terjadi Kesalahan silahkan Hubungi Developer! ");
    return;
  }
  errorNotification();
  var button = form.find('button[type="submit"]');
  buttonLoading(button, false);
}

function successNotification(msg = "Data saved successfully", timer = 2000) {
  swalToast.fire({
    icon: "success",
    title: msg,
    timer: timer,
  });
}

function errorNotification(msg = "Failed to save data") {
  swalToast.fire({
    icon: "error",
    title: msg,
  });
}

function generateCsrf() {
  return $.get(adminModulUrl + "authorization/generateCsrf");
}

$(document).on("click", ".initiate_form_token", function (e) {
  let form = $(this).attr("data-target") || $(this).attr("data-bs-target");

  // reset form
  if ($(form).find("form").length) {
    $(form).find("form").trigger("reset");
  }
  initiateFormTokenValue(form, "db_token");
});

$(document).ready(function (e) {
  console.log("Script Loaded");
  // add config
  $("#add_config").click(function (e) {
    let site_id = $(this).data("site_id");
    if (site_id == undefined) {
      console.log("site id not found");
    }
    $("#form_config").find('[name="site"]').val(site_id);
  });
});

function randomString(L = 20) {
  var s = "";
  var randomchar = function () {
    var n = Math.floor(Math.random() * 62);
    if (n < 10) return n; //1-10
    if (n < 36) return String.fromCharCode(n + 55); //A-Z
    return String.fromCharCode(n + 61); //a-z
  };
  while (s.length < L) s += randomchar();
  return s;
}

function initiateFormTokenValue(form, additional = false) {
  form = $(form);
  let newToken = randomString();
  if (additional) {
    if (form.find(`input[name="${additional}"]`).length) {
      form.find(`input[name="${additional}"]`);
    }
  }
  form.find('input[name="form_token"]').val(newToken);
  form.find('input[name="token"]').val(newToken);
}

function deleteConfirm(url, id, element_to_remove = false, callback = false) {
  var targetUrl = url;

  Swal.fire({
    title: "Are you sure want to delete this ?",
    text: "This data can't be returned",
    icon: "warning",
    showCancelButton: true,
    confirmButtonColor: "#3085d6",
    cancelButtonColor: "#d33",
    confirmButtonText: "Yes, i'm sure",
  }).then(function (res) {
    if (!res.isConfirmed) {
      console.info("Canceled");
      return;
    }
    $.ajax({
      type: "post",
      url: targetUrl,
      data: {
        id: id,
      },
      success: function (response) {
        /** show_json and json_encode conflict */
        try {
          var json = $.parseJSON(response);
        } catch (e) {
          var json = response;
        }

        /** doing msg response here */
        ajaxResponse(
          json,
          (statusText = false),
          (xhr = false),
          ($form = false)
        );

        if (json.error == 0) {
          if (element_to_remove) {
            element_to_remove.fadeOut(500, function () {
              $(this).remove();
            });
          }
          runCallBack(false, false, callback);
        }
      },
    });
  });
}

function currentModulUrl(segment) {
  // get the segments
  pathArray = window.location.pathname.split("/");
  // find where the segment is located
  indexOfSegment = pathArray.indexOf(segment);
  // make base_url be the origin plus the path to the segment
  return (
    window.location.origin + pathArray.slice(0, indexOfSegment).join("/") + "/"
  );
}
