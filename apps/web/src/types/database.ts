/**
 * Placeholder for Supabase's generated schema types.
 *
 * Once a real Supabase project exists and the migrations in
 * supabase/migrations/ have been applied, generate the real types with:
 *
 *   npx supabase gen types typescript --project-id <your-project-ref> > src/types/database.ts
 *
 * and remove this placeholder. Until then, `Database` is left as `any` so
 * the Supabase client below type-checks without a live schema to read —
 * every query is effectively untyped in the meantime, which is the correct
 * honest state (there is nothing to type-check against yet), not a bug to
 * paper over.
 */
export type Database = any; // eslint: no-explicit-any is not part of this project's lint config
