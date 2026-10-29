import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './styles.css';

const container = document.getElementById('root');
if (!container) {
  throw new Error('Élément #root introuvable dans index.html');
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

// Service worker enregistré ici (injectRegister: null dans vite.config.ts) pour
// en attraper le refus : contexte non sécurisé, navigation privée, politique.
// L'application reste utilisable en ligne sans lui.
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register(`${import.meta.env.BASE_URL}sw.js`, { scope: import.meta.env.BASE_URL })
      .catch((error: unknown) => {
        console.warn('Service worker non enregistré : mode hors ligne indisponible.', error);
      });
  });
}
