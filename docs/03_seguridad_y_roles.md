# Seguridad, roles y salida controlada

## Capas de defensa

1. Open WebUI no toca la base financiera.
2. La API segura valida login y token.
3. La API valida permisos por acción.
4. La API valida acceso por tablas.
5. Internet está bloqueado por defecto.
6. El acceso externo requiere 4 condiciones simultáneas:
   - permiso `ask_hybrid`
   - `web_access_enabled=true` en el usuario
   - usuario incluido en `INTERNET_ALLOWED_USERS`
   - `global_internet_enabled=true`
7. La query externa se sanitiza para no exponer datos corporativos.
8. La respuesta separa hechos internos y conceptos externos.

## Roles por default

### admin

- administración total
- acceso a todas las tablas
- puede habilitar o bloquear internet
- puede controlar cola de red del host

### analyst

- consulta interna operativa
- sin benchmark web por default

### auditor

- consulta interna
- puede usar benchmark web controlado

### viewer

- lectura resumida

## Tablas sensibles

- `prompt_audit`
- `policy_audit`
- `assignments`

Puedes restringirlas por rol desde la UI segura.
