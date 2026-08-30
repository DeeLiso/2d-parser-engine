(function () {
    try {
        var dark = localStorage.getItem('darkMode') === '1';
        var root = document.documentElement;
        root.classList.toggle('dark', dark);
        if (dark) {
            root.style.colorScheme = 'dark';
        } else {
            root.style.colorScheme = 'light';
        }
    } catch (e) { }
})();
