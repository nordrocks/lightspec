## Блокировка аккаунта
Изменение: MODIFIED
Источник: feature:007-login-lockout
Причина: None
Контракты: contract:public-api.login, contract:events.account-locked, contract:public-api.unlock

### Как работает

```mermaid
stateDiagram-v2
    [*] --> active
    active --> locked: пятый неудачный вход подряд
    locked --> active: блокировка истекла или ссылка из письма
```

Счётчик и токен разблокировки contract:public-api.unlock. Токен хранится в базе: adr:unlock-token-storage.
