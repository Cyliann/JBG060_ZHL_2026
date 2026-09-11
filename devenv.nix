{ pkgs, ... }:
{
  languages.python = {
    enable = true;
    venv.enable = true;
    uv = {
      enable = true;
      sync.enable = true;
    };
  };

  packages = with pkgs; [
    qgis
    zlib # needed for numpy libz.so.1
  ];
}
