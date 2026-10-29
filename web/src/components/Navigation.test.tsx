import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { App } from '../App';
import { Navigation } from './Navigation';
import type { Lang, NavKey } from '../i18n';

const noop = () => {};

function render(lang: Lang, active: NavKey): string {
  return renderToString(
    <Navigation lang={lang} active={active} onNavigate={noop} onLangChange={noop} />,
  );
}

describe('Navigation', () => {
  it('affiche les six entrées en français et « + Ajouter »', () => {
    const html = render('fr', 'today');
    for (const label of ['Aujourd’hui', 'Planning', 'Chevaux', 'Santé', 'Courses', 'Plus']) {
      expect(html).toContain(`>${label}</button>`);
    }
    expect(html.match(/data-nav="/g)).toHaveLength(6);
    expect(html).toContain('>+ Ajouter</button>');
    expect(html).toContain('aria-label="Navigation principale"');
  });

  it('affiche les six entrées en anglais et « + Add »', () => {
    const html = render('en', 'today');
    for (const label of ['Today', 'Planning', 'Horses', 'Health', 'Races', 'More']) {
      expect(html).toContain(`>${label}</button>`);
    }
    expect(html).toContain('>+ Add</button>');
    expect(html).toContain('aria-label="Main navigation"');
  });

  it('marque l’entrée active, la langue pressée et démarre en français', () => {
    const html = render('en', 'horses');
    expect(html.match(/aria-current="page"/g)).toHaveLength(1);
    expect(html).toMatch(/data-nav="horses" aria-current="page"/);
    expect(html).toMatch(/lang="en" aria-pressed="true"/);
    expect(html).toMatch(/lang="fr" aria-pressed="false"/);
    // « + Ajouter » est frère de <nav>, jamais dans la barre.
    expect(html).toMatch(/<\/nav><button type="button" class="add">/);

    expect(renderToString(<App />)).toContain('<h1>Aujourd’hui</h1>');
  });
});
