// main.js — vanilla JS only

// Delete confirmation popup on the profile page
(function () {
    var dialog = document.getElementById("delete-dialog");
    var forms = document.querySelectorAll("form[data-confirm-delete]");
    if (!forms.length) {
        return;
    }

    var pendingForm = null;

    forms.forEach(function (form) {
        form.addEventListener("submit", function (event) {
            event.preventDefault();
            if (dialog && typeof dialog.showModal === "function") {
                pendingForm = form;
                dialog.showModal();
            } else if (window.confirm("Delete this expense? This cannot be undone.")) {
                form.submit();
            }
        });
    });

    if (!dialog) {
        return;
    }

    dialog.querySelector("[data-confirm-cancel]").addEventListener("click", function () {
        pendingForm = null;
        dialog.close();
    });

    dialog.querySelector("[data-confirm-ok]").addEventListener("click", function () {
        var form = pendingForm;
        pendingForm = null;
        dialog.close();
        if (form) {
            form.submit();
        }
    });
})();
