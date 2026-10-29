import { useEffect, useState } from 'react';
import { Navigation } from './components/Navigation';
import { t } from './i18n';
import type { Lang, NavKey } from './i18n';

export function App() {
  const [lang, setLang] = useState<Lang>('fr');
  const [active, setActive] = useState<NavKey>('today');

  // <html> est hors de la racine React : l'effet synchronise un système externe (WCAG 3.1.1).
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  return (
    <>
      <Navigation lang={lang} active={active} onNavigate={setActive} onLangChange={setLang} />
      <main className="main">
        <h1>{t(lang, active)}</h1>
      </main>
    </>
  );
}
