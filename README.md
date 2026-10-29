# Blue Stinger Director's Cut

Blue Stinger came out first in Japan. When it was released in the US and Europe, the publisher, Activision, requested Climax Graphics to changethe camera to use a 3rd person view constantly. This bizarre (and honestly bad) decision was mage against the original team behind the game. The Japanese version keeps the camera angles the studio wanted, which is a moving, sometimes fixed angles, that actually serve the gameplay way more. In this japanese version, the voices are already in English, but all the text is in Japanese.

This patch takes the Japanese game and puts the western text in it. So you get the Japanese cameras and gameplay with English or French text.

There are two versions:

- EN: Japanese game + US version. Japanese cameras, all menus and text in English, and also using the English textures. Like the US release, the voiced lines have no subtitles.

- FR: Japanese game + French PAL version. Japanese cameras, all menus and text in French, French textures, and every voiced line is subtitled (the French release was the only one with full subtitles).

No game data is included here. You need your own dumps of the games (Japanese + either US or PAL FR), and the script builds the patched disc from them.

Fully tested on a real Dreamcast with GDEMU and on Flycast. I played a big part of the game with it on a real Dreamcast without a single issue or crash. If you see any mistakes or fixes, let me know! 

## About

This is a fan work. I grew up playing the PAL version of Blue Stinger and actually really enjoyed it, and only recently found out the Japanese version had different camera angles. After so long, I wanted to play it the way it was made, in a language I could read, so here it is!

Made in hommage to Shinya Nishigaki (1962-2004), Climax Graphics / Crazy Games, Sega and the Dreamcast.

This project is not endorsed or approved by Sega.

Special thanks to Spyounet, for making me aware of the Japanese version changes in his video about Illbleed and Nishigaki: https://youtu.be/vMokrFV17Xw

Go and subscribe to his channel and check his videos!

## What you need

GDI dumps (track01.bin, track02.raw, track03.bin + the .gdi file) of:

| For | Game | TOSEC name |
|---|---|---|
| both | Japanese v1.006 | Blue Stinger v1.006 (1999)(Sega)(JP)[!] |
| EN | US v1.000 | Blue Stinger v1.000 (1999)(Activision)(NTSC)(US)[!] |
| FR | French PAL v1.000 | Blue Stinger v1.000 (1999)(Activision)(PAL)(FR)[!] |

MD5 of track03.bin, to check your dumps:

```
ca82462fdc24da063de2c4375a04bd36  Japanese v1.006
dd75046cc9f212a5d939cd823971527f  US v1.000
eb09dfde4408014b09e525e335e88f3c  French PAL v1.000
```

The script checks the game executable itself, so it will tell you if a disc is not the right version.

And on your computer:

- Python 3 (nothing else to install)
- about 1.3 GB of free space

It works on Windows, Linux and macOS. On Windows, type `python` instead of `python3`.

## How to build

Unzip your games somewhere, then run:

```
python3 patch.py en "path/to/JP/Blue Stinger (JP).gdi" "path/to/US/Blue Stinger (US).gdi"
```

or for the French version:

```
python3 patch.py fr "path/to/JP/Blue Stinger (JP).gdi" "path/to/FR/Blue Stinger (FR).gdi"
```

It takes a few seconds. You get a folder `Blue Stinger Director's Cut (EN)` (or FR) with the new GDI inside. You can give another output folder as last argument if you want.

Load the .gdi in your emulator, or put it on your ODE (GDEMU etc.) like any other GDI.

## What the patch does

The game executable, the cameras, the scripts and the gameplay are all from the Japanese version. On top of that:

- Room text: every dialogue, message and subtitle in the rooms are replaced with the western one. The text block of each room is swapped, the Japanese script around it is kept.
- Menus and items: the item names, place names, menus, yes/no choices etc. are inside the executable. The western text is longer than the Japanese one and did not fit, so I moved all of it to a free area after the end of the program, and every pointer to it is updated.
- Font: the Japanese font has no lowercase letters and no accents. The western letters (and the French accents) are added to the font, in place of kanji the game never uses. The letter spacing of the dialogue text is taken from the western version.
- Textures: signs, notices and labels that were translated in the western version are swapped in. The French version also gets the French menu labels.
- Videos: the videos with Japanese text in them are replaced with the western ones. In the French version that includes the French ending.
- Opening trailer: the Japanese disc has a trailer that plays when you leave the title screen alone. The western discs don't have it. It is cut down to one second of black, silent video, to make room on the disc for the bigger French videos.
- Subtitle timing (FR): the French release fixed the timing of a few cutscenes so the subtitles stay in sync with the voices. Those fixes are used too!
- Save name: the save description shown in the Dreamcast memory card menu is in English instead of Japanese.

The disc is then rebuilt with all the files at their new size, and all the sector checksums are redone.

## Good to know

- The title screen is still the Japanese one. I found it to be cooler than the US/PAL title, so I decide dto leave it. It's the only place with Japanese left.
- A few lines don't exist in the western versions, so I wrote them (in English and French): the casino entrance messages (the western releases removed them), the "item acquired" message, and the save name. Everything else is the official translation.
- The US version translated both "Equip" and "Use" as "Use" in the item menu. I kept it like that for authenticity sake.
- The EN version has no subtitles on voiced lines, same as the original US release.

## Files

- `patch.py`: the patcher
- `lib/gdi.py`: reads and rebuilds the GDI
- `lib/roomfmt.py`: room file format
- `lib/bscode.py`: the game's text encoding
- `lib/ecc.py`: sector checksums (EDC/ECC)

## License

The patcher code is under the GNU GPL v3, see `LICENSE`. The game itself and its data belong to Sega and are not included here.
