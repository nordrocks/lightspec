## Блокировка аккаунта
Изменение: MODIFIED
Источник: feature:012-unlock-link
Причина: None
Контракты: contract:public-api.login, contract:events.account-locked

### Как работает

```mermaid
stateDiagram-v2
    [*] --> active
    active --> locked: пятый неудачный вход подряд
    locked --> active: блокировка истекла
```

Счётчик неудачных попыток хранится по аккаунту: adr:postgres.
