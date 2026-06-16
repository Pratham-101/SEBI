{ pkgs }: {
  deps = [
    pkgs.python311
    pkgs.python311Packages.pip
    # System libraries Playwright/Chromium needs at runtime.
    pkgs.glib
    pkgs.nss
    pkgs.nspr
    pkgs.dbus
    pkgs.atk
    pkgs.cups
    pkgs.libdrm
    pkgs.gtk3
    pkgs.pango
    pkgs.cairo
    pkgs.libxkbcommon
    pkgs.mesa
    pkgs.expat
    pkgs.xorg.libX11
    pkgs.xorg.libXcomposite
    pkgs.xorg.libXdamage
    pkgs.xorg.libXext
    pkgs.xorg.libXfixes
    pkgs.xorg.libXrandr
    pkgs.xorg.libxcb
    pkgs.alsa-lib
  ];
}
