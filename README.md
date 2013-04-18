# Floobits Vim Plugin

## Development status: not at all working yet. Stay tuned.

## Installation

Assuming you have Vundle or Pathogen:

1. `cd ~/.vim/bundle` and `git clone https://github.com/Floobits/vim-plugin Floobits`
1. Add `Bundle 'Floobits'` to your `~/.vimrc`
1. Add your Floobits username and API secret to `~/.floorc`.

A typical floorc looks like this:

    username myuser
    secret gii9Ka8aZei3ej1eighu2vi8D

## Usage

* To join a room, use `:FlooJoinRoom https://floobits.com/r/room_owner/room_name/`. Room urls are the same as what you see in the web editor.
* To part a room, use `:FlooPartRoom`.
