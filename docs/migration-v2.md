# Migration v1.x → v2.0

## Breaking Changes

### 1. role_overrides nyní aplikovány
`compute_cw()` v engine čte `role_overrides` z `cw_heuristics.yaml` a aplikuje je podle `person.role`. CW hodnoty se změní pro non-Dev role:

| Role | Evidence | v1.x CW | v2.0 CW |
|------|----------|---------|---------|
| Arch | reviewer | 0.25 | **0.30** |
| PM | consulted | 0.15 | **0.20** |
| BO | consulted | 0.15 | **0.30** |
| Dev | owner | 1.00 | 1.00 (beze změny) |

### 2. Multi-contract support
Person schema má nová volitelná pole:
- `contract` — typ smlouvy (HPP, DPČ, External)
- `evidence_scope` — fnmatch patterns pro item IDs
- `evidence_default` — true = fallback pro nescopované signály

### 3. Demo data
Alice je rozdělen na `alice-arch` (40h) + `alice-pm` (20h).

## Co udělat

1. **Zkontrolovat CW reporty** — hodnoty se změní pro Arch, PM, BO
2. **Volitelně přidat `contract` pole** do `people.yaml` pro multi-contract
3. **Volitelně přidat `evidence_scope`** pro automatické routování
4. **Re-spustit EDPA** na posledních iteracích a porovnat s v1.x výstupy

## Zpětná kompatibilita

- Všechny v1.x `people.yaml` soubory fungují beze změny
- Nová pole jsou volitelná
- Pokud `role_overrides` v heuristice chybí, chování identické s v1.x
- Pokud `evidence_scope` chybí, veškerá evidence jde na osobu (jako v1.x)
