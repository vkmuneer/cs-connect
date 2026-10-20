// Small progressive enhancements — the portal works without JavaScript.
(function () {
  "use strict";

  // Mobile navigation
  var toggle = document.querySelector(".nav-toggle");
  var links = document.querySelector(".nav .links");
  if (toggle && links) {
    toggle.addEventListener("click", function () {
      var open = links.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  // Confirm destructive actions
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.getAttribute("data-confirm"))) {
        event.preventDefault();
      }
    });
  });

  // Reveal employer fields only when the provider box is ticked
  document.querySelectorAll("[data-toggle-target]").forEach(function (input) {
    var target = document.querySelector(input.getAttribute("data-toggle-target"));
    if (!target) return;
    var sync = function () { target.hidden = !input.checked; };
    input.addEventListener("change", sync);
    sync();
  });

  // Narrow the programme list to the chosen department
  document.querySelectorAll("[data-programme-map]").forEach(function (scope) {
    var map;
    try {
      map = JSON.parse(scope.getAttribute("data-programme-map") || "{}");
    } catch (e) {
      return;
    }
    var department = scope.querySelector("[name=department]");
    var programme = scope.querySelector("[name=programme]");
    if (!department || !programme || department.type === "hidden") return;

    var all = Array.prototype.map.call(programme.options, function (option) {
      return { value: option.value, label: option.textContent };
    });

    var sync = function () {
      var chosen = department.value;
      var allowed = all.filter(function (item) {
        return !chosen || String(map[item.value]) === String(chosen);
      });
      if (!allowed.length) allowed = all;
      var current = programme.value;
      programme.innerHTML = "";
      allowed.forEach(function (item) {
        var option = document.createElement("option");
        option.value = item.value;
        option.textContent = item.label;
        programme.appendChild(option);
      });
      if (allowed.some(function (i) { return i.value === current; })) {
        programme.value = current;
      }
    };
    department.addEventListener("change", sync);
    sync();
  });

  // Dismiss flash messages on click
  document.querySelectorAll(".alert").forEach(function (alert) {
    alert.addEventListener("click", function () { alert.remove(); });
  });
})();
