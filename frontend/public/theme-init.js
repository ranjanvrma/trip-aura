// Applies the saved theme before the first paint, so a light-theme visitor never sees a dark flash.
// A separate file because the content security policy does not allow inline scripts.
try {
  if (localStorage.getItem("tripaura.theme") === "light") {
    document.documentElement.dataset.theme = "light";
    document.querySelector('meta[name="theme-color"]').setAttribute("content", "#f6f4ef");
  }
} catch (e) { /* storage blocked: stay on the default theme */ }
