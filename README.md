# Floobits Vim Plugin

## Development status: Two way syncing works, but this plugin is not well-tested and not fully-featured.

## Installation

Assuming you have Vundle or Pathogen:

1. `cd ~/.vim/bundle` and `git clone https://github.com/Floobits/vim-plugin Floobits`
1. Vundle users: Add `Bundle 'Floobits'` to your `~/.vimrc`
1. Add your Floobits username and API secret to `~/.floorc`.

A typical floorc looks like this:

    username myuser
    secret gii9Ka8aZei3ej1eighu2vi8D

## Usage

* To join a room, use `:FlooJoinRoom https://floobits.com/r/room_owner/room_name/`. Room urls are the same as what you see in the web editor.
* To part a room, use `:FlooPartRoom`.
* To toggle follow mode, use `:FlooToggleFollowMode`.
* To make everyone else go to your cursor, use `:FlooPing`.

## Troubleshooting

Other plugins can interfere with Floobits. For example, [YouCompleteMe](https://github.com/Valloric/YouCompleteMe) changes `updatetime` to 2000 milliseconds. This causes increased latency and decreased reliability when collaborating. If you experience problems, try disabling other plugins before submitting a bug report.
