async ({ quietMs, timeoutMs }) => {
    const root = document.documentElement;
    if (!root) return true;

    return await new Promise((resolve) => {
        let done = false;
        let timer = null;

        const finish = () => {
            if (done) return;
            done = true;
            if (timer) clearTimeout(timer);
            observer.disconnect();
            resolve(true);
        };

        let last = Date.now();
        const observer = new MutationObserver(() => {
            last = Date.now();
        });

        observer.observe(root, {
            subtree: true,
            childList: true,
            attributes: true,
            characterData: true,
        });

        const check = () => {
            if (done) return;
            const quietFor = Date.now() - last;
            if (quietFor >= quietMs) {
                finish();
                return;
            }
            timer = setTimeout(check, quietMs);
        };

        timer = setTimeout(check, quietMs);
        setTimeout(finish, timeoutMs);
    });
};
