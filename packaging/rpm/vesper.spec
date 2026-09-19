# Ricetta per Fedora / openSUSE / RHEL. Stesso install.sh, layout identico:
# cambiano solo i nomi dei pacchetti richiesti.
Name:           vesper
Version:        0.1.1
Release:        1%{?dist}
Summary:        Ambiente desktop leggero in Python + GTK3 su Openbox
License:        AGPL-3.0-or-later
URL:            https://github.com/thecloners21/vesper
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

Requires:       openbox
Requires:       python3
Requires:       python3-gobject
Requires:       python3-cairo
Requires:       gtk3
Requires:       wmctrl
Requires:       xrandr

Recommends:     dunst
Recommends:     xautolock
Suggests:       picom
Suggests:       lxappearance
Suggests:       brightnessctl

%description
Vesper è un ambiente desktop completo e leggero: pannello con menu delle
applicazioni e applet, Centro di Controllo, file manager proprio (finestra e
desktop con sfondo e icone), salvaschermo con blocco schermo e preset di
aspetto che cambiano insieme colore d'accento, sfondo, set di icone e tema
delle finestre. Dopo l'installazione compare fra le sessioni del gestore di
accesso.

%prep
%autosetup

%install
DESTDIR=%{buildroot} sh ./install.sh --prefix=%{_prefix}
find %{buildroot} -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

%files
%license LICENSE
%doc README.md
%{_bindir}/vesper-*
%{_prefix}/lib/vesper/
%{_datadir}/vesper/
%{_datadir}/themes/Vesper-*
%{_datadir}/themes/1977-*
%{_datadir}/xsessions/vesper.desktop
%{_datadir}/applications/vesper-*.desktop
%{_datadir}/icons/hicolor/scalable/apps/vesper-logo*.svg

%changelog
* Sat Sep 19 2026 Daniele Deplano <deplano.d@gmail.com> - 0.1.1-1
- Prima versione pacchettizzata.
