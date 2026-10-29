export type Lang = 'fr' | 'en';

export const LANGS = ['fr', 'en'] as const satisfies readonly Lang[];

export const NAV_KEYS = ['today', 'planning', 'horses', 'health', 'races', 'more'] as const;

export type NavKey = (typeof NAV_KEYS)[number];

export type MessageKey = NavKey | 'add' | 'navLabel' | 'langLabel';

const MESSAGES: Record<Lang, Record<MessageKey, string>> = {
  fr: {
    today: 'Aujourd’hui',
    planning: 'Planning',
    horses: 'Chevaux',
    health: 'Santé',
    races: 'Courses',
    more: 'Plus',
    add: '+ Ajouter',
    navLabel: 'Navigation principale',
    langLabel: 'Langue',
  },
  en: {
    today: 'Today',
    planning: 'Planning',
    horses: 'Horses',
    health: 'Health',
    races: 'Races',
    more: 'More',
    add: '+ Add',
    navLabel: 'Main navigation',
    langLabel: 'Language',
  },
};

export function t(lang: Lang, key: MessageKey): string {
  return MESSAGES[lang][key];
}
