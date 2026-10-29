import { readFileSync } from 'node:fs';

/** MCD V0, loaded verbatim: schema/graffard_racing_mcd_v0.sql is never modified. */
export const migration0001 = {
  id: '0001_mcd_v0',
  sql: readFileSync(new URL('../../../../schema/graffard_racing_mcd_v0.sql', import.meta.url), 'utf8'),
};
