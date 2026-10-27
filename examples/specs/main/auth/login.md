# Вход: документация
Источник: feature:007-login-lockout

Вход по паролю, блокировка аккаунта и сессии.

## Блокировка аккаунта
Источник: feature:015-drop-unlock
Контракты: contract:public-api.login, contract:events.account-locked

### Как работает

```mermaid
stateDiagram-v2
    [*] --> active
    active --> locked: пятый неудачный вход подряд
    locked --> active: блокировка истекла
```

Счётчик неудачных попыток хранится по аккаунту: adr:postgres.

## Сессии
Источник: feature:007-login-lockout
Контракты: contract:public-api.session, contract:public-api.refresh

### Как работает

```mermaid
sequenceDiagram
    Клиент->>Система: public-api.login
    Система-->>Клиент: public-api.session
    Note over Клиент,Система: public-api.refresh
    Клиент->>Система: refreshToken
    Система-->>Клиент: новая public-api.session
```

| Токен | Для чего | Как проверяется |
|---|---|---|
| `token` | вызовы с доступом «пользователь» | по подписи, без обращения к хранилищу |
| `refreshToken` | продление сессии | по записи в хранилище, поэтому его можно отозвать |
