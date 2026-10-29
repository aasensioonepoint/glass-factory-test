/*
 * Client de l'API Graffard, contrat de T3 (connexion par persona de démonstration) :
 *   GET  /api/personas            → [{compteId, nom, role}]
 *   POST /api/session {compteId}  → {jeton, compte}
 *   GET  /api/moi                 → compte
 * Le jeton vit en mémoire et, quand il est disponible, dans `sessionStorage`
 * (try/catch : navigation privée, politique du site). Toute réponse 401 vide la
 * session. Les réponses sont des DONNÉES non fiables : leur forme est vérifiée
 * avant d'atteindre l'interface, jamais transtypée.
 */

/** Libellés de rôle de T2, à l'identique. */
export const ROLES = [
  'entraineur',
  'assistant_entraineur',
  'cavalier',
  'veterinaire',
  'charge_engagements',
  'proprietaire',
] as const;

export type Role = (typeof ROLES)[number];

/** Identifiant de compte : `bigint` en base, sérialisé en chaîne ou en nombre selon le pilote SQL. */
export type CompteId = string | number;

export interface Persona {
  compteId: CompteId;
  nom: string;
  role: Role;
}

export interface Compte {
  compteId: CompteId;
  roles: Role[];
  /** Absent du contrat de T3 ; lu s'il est fourni. */
  nom?: string;
}

export type ErreurApi = 'reseau' | 'non_autorise' | 'http' | 'reponse_invalide';

export type Resultat<T> = { ok: true; valeur: T } | { ok: false; erreur: ErreurApi };

export interface ApiClient {
  personas(): Promise<Resultat<Persona[]>>;
  connecter(compteId: CompteId): Promise<Resultat<Compte>>;
  moi(): Promise<Resultat<Compte>>;
  /** Oublie le jeton (mémoire et stockage). */
  deconnecter(): void;
  /** Jeton courant, ou `null` sans session. */
  jeton(): string | null;
}

/** Clé du jeton dans `sessionStorage`. */
export const JETON_STORAGE_KEY = 'graffard.jeton';

/** Délai au-delà duquel une requête est tenue pour une erreur réseau. */
export const DELAI_REQUETE_MS = 10_000;

export type JetonStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

type Fetch = (input: string, init: RequestInit) => Promise<Response>;

/** `sessionStorage`, ou `null` s'il est absent ou refusé. */
export function sessionStore(): JetonStorage | null {
  try {
    return globalThis.sessionStorage ?? null;
  } catch {
    return null;
  }
}

function lireJeton(storage: JetonStorage | null): string | null {
  try {
    const stored = storage?.getItem(JETON_STORAGE_KEY);
    return typeof stored === 'string' && stored !== '' ? stored : null;
  } catch {
    return null;
  }
}

function enregistrement(valeur: unknown): valeur is Record<string, unknown> {
  return typeof valeur === 'object' && valeur !== null && !Array.isArray(valeur);
}

export function estRole(valeur: unknown): valeur is Role {
  return typeof valeur === 'string' && (ROLES as readonly string[]).includes(valeur);
}

function estCompteId(valeur: unknown): valeur is CompteId {
  return (
    (typeof valeur === 'string' && valeur !== '') ||
    (typeof valeur === 'number' && Number.isSafeInteger(valeur))
  );
}

/** Liste de personas validée, ou `null` si la forme ne tient pas le contrat. */
export function lirePersonas(valeur: unknown): Persona[] | null {
  if (!Array.isArray(valeur)) return null;
  const personas: Persona[] = [];
  for (const item of valeur) {
    if (!enregistrement(item)) return null;
    const { compteId, nom, role } = item;
    if (!estCompteId(compteId) || typeof nom !== 'string' || nom === '' || !estRole(role)) {
      return null;
    }
    personas.push({ compteId, nom, role });
  }
  return personas;
}

/** Compte validé, ou `null` si la forme ne tient pas le contrat. */
export function lireCompte(valeur: unknown): Compte | null {
  if (!enregistrement(valeur)) return null;
  const { compteId, roles, nom } = valeur;
  if (!estCompteId(compteId) || !Array.isArray(roles) || !roles.every(estRole)) return null;
  if (nom !== undefined && typeof nom !== 'string') return null;
  return nom === undefined ? { compteId, roles: [...roles] } : { compteId, roles: [...roles], nom };
}

export interface ClientOptions {
  fetch?: Fetch;
  storage?: JetonStorage | null;
  base?: string;
  delaiMs?: number;
}

export function creerClient(options: ClientOptions = {}): ApiClient {
  const fetcher: Fetch = options.fetch ?? ((input, init) => globalThis.fetch(input, init));
  const storage = options.storage ?? null;
  const base = options.base ?? '';
  const delaiMs = options.delaiMs ?? DELAI_REQUETE_MS;
  let jeton = lireJeton(storage);

  function ecrireJeton(valeur: string): void {
    jeton = valeur;
    try {
      storage?.setItem(JETON_STORAGE_KEY, valeur);
    } catch {
      // Stockage refusé ou plein : le jeton reste en mémoire pour cet onglet.
    }
  }

  function effacerJeton(): void {
    jeton = null;
    try {
      storage?.removeItem(JETON_STORAGE_KEY);
    } catch {
      // Stockage refusé : la mémoire est déjà vidée.
    }
  }

  async function requete(
    methode: 'GET' | 'POST',
    chemin: string,
    corps?: unknown,
    avecJeton = true,
  ): Promise<Resultat<unknown>> {
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (avecJeton && jeton !== null) headers.Authorization = `Bearer ${jeton}`;
    const init: RequestInit = { method: methode, headers };
    if (corps !== undefined) {
      headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(corps);
    }
    if (typeof AbortSignal.timeout === 'function') init.signal = AbortSignal.timeout(delaiMs);

    let reponse: Response;
    try {
      reponse = await fetcher(`${base}${chemin}`, init);
    } catch {
      return { ok: false, erreur: 'reseau' };
    }
    if (reponse.status === 401) {
      effacerJeton();
      return { ok: false, erreur: 'non_autorise' };
    }
    if (!reponse.ok) return { ok: false, erreur: 'http' };
    try {
      return { ok: true, valeur: (await reponse.json()) as unknown };
    } catch {
      return { ok: false, erreur: 'reponse_invalide' };
    }
  }

  function valider<T>(brut: Resultat<unknown>, lire: (v: unknown) => T | null): Resultat<T> {
    if (!brut.ok) return brut;
    const valeur = lire(brut.valeur);
    return valeur === null ? { ok: false, erreur: 'reponse_invalide' } : { ok: true, valeur };
  }

  return {
    async personas() {
      return valider(await requete('GET', '/api/personas'), lirePersonas);
    },

    async connecter(compteId) {
      // Un ancien jeton n'est pas envoyé : la connexion en ouvre une nouvelle.
      const brut = await requete('POST', '/api/session', { compteId }, false);
      const session = valider(brut, (v) => {
        if (!enregistrement(v) || typeof v.jeton !== 'string' || v.jeton === '') return null;
        const compte = lireCompte(v.compte);
        return compte === null ? null : { jeton: v.jeton, compte };
      });
      if (!session.ok) return session;
      ecrireJeton(session.valeur.jeton);
      return { ok: true, valeur: session.valeur.compte };
    },

    async moi() {
      if (jeton === null) return { ok: false, erreur: 'non_autorise' };
      return valider(await requete('GET', '/api/moi'), lireCompte);
    },

    deconnecter: effacerJeton,

    jeton: () => jeton,
  };
}

/** Client de l'application : `fetch` du navigateur, jeton dans `sessionStorage`. */
export const api: ApiClient = creerClient({ storage: sessionStore() });
