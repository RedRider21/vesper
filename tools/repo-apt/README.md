# Repository APT per i clienti con licenza commerciale

Serve a due cose insieme: consegnare gli aggiornamenti a chi ha la licenza
commerciale, e **contare** quante macchine li scaricano. Il secondo è il
motivo vero: è l'unico contatore che non richiede di mettere niente dentro il
prodotto, perché il cliente usa il repository di sua volontà — vuole le patch.

## Come si monta

```sh
# 1. una chiave GPG per firmare il repository (una volta sola)
gpg --quick-generate-key "Vesper Repo <deplano.d@gmail.com>" default default never

# 2. costruire il pacchetto commerciale e pubblicarlo
./tools/make-deb.sh --commerciale
./tools/repo-apt/crea-repo.sh --repo /srv/vesper-repo \
    --deb packaging/vesper_0.5.0_all_commerciale.deb --gpg "Vesper Repo"
```

## Il token per cliente

Ogni cliente riceve un token casuale nell'URL. Con nginx:

```nginx
server {
    listen 443 ssl;
    server_name repo.example.com;

    # /t/<token>/... -> la stessa cartella per tutti, ma il token resta nei log
    location ~ ^/t/([A-Za-z0-9_-]{16,})/(.*)$ {
        # elenco dei token attivi: una riga "token 1;" per cliente
        set $tok $1;
        if ($tok !~ ^(3f9ab2c1d4e5f6a7|9911aabbccddeeff)$) { return 403; }
        alias /srv/vesper-repo/$2;
        autoindex off;
    }
    access_log /var/log/nginx/vesper-repo.access.log combined;
}
```

Token: `head -c 12 /dev/urandom | base32 | tr -d = | tr A-Z a-z`. Revocare un
cliente significa toglierlo dall'elenco.

Riga da dare al cliente, in `/etc/apt/sources.list.d/vesper.list`:

```
deb [signed-by=/usr/share/keyrings/vesper.gpg] https://repo.example.com/t/<token>/ stabile main
```

più la chiave pubblica:

```sh
sudo curl -fsSL https://repo.example.com/t/<token>/chiave-pubblica.asc \
  | sudo gpg --dearmor -o /usr/share/keyrings/vesper.gpg
```

In alternativa al token nell'URL si può usare l'autenticazione HTTP di base:
finisce comunque nei log come nome utente, e il contatore la legge lo stesso.

## Contare

```sh
tools/repo-apt/conta-installazioni.py --clienti clienti.json \
    /var/log/nginx/vesper-repo.access.log
```

`clienti.json` associa token, nome e postazioni concordate:

```json
{
  "3f9ab2c1d4e5f6a7": {"cliente": "Acme S.p.A.", "postazioni": 50},
  "9911aabbccddeeff": {"cliente": "Beta srl", "postazioni": 25}
}
```

**Attenzione a cosa dice quel numero.** Conta indirizzi distinti, non
macchine: dietro un NAT aziendale cento computer sono un indirizzo solo, e un
portatile ne cambia parecchi in un mese. Sottostima in ufficio, sovrastima con
gli indirizzi dinamici. Vale come **segnale**: se un cliente con 25 postazioni
mostra 60 indirizzi distinti, è il momento di chiedere il rapporto firmato.

Il conteggio che fa fede è quello delle installazioni:

```sh
# sul computer del cliente, per ogni macchina
vesper-licenza --rapporto --out rapporto-pc1.json
# il cliente li unisce e manda un file solo
vesper-licenza --unisci rapporto-*.json --out rapporto-acme.json
# qui
tools/vesper-licgen.py conta --licenza acme.licenza.json rapporto-acme.json
```

## Cosa mettere nel contratto

Perché i log abbiano valore in una discussione, il contratto deve dirlo:

> Gli aggiornamenti sono erogati tramite il repository del licenziante,
> accessibile con le credenziali assegnate. Il licenziatario si impegna a non
> ridistribuirle e a non mettere il repository a disposizione di macchine
> eccedenti quelle licenziate. I registri di accesso del repository e i
> rapporti di installazione firmati fanno fede ai fini della riconciliazione
> periodica.
