# [Floobits](https://floobits.com/) Vim Plugin

Real-time collaborative editing. Think Etherpad, but with native editors. This is the plugin for Vim. We're also working on plugins for [Emacs](https://github.com/Floobits/emacs-plugin) and [Sublime Text](https://github.com/Floobits/sublime-text-2-plugin).

## Development status: This plugin is fairly stable.  Unfortunately, vim doesn't make it possible to have an event loop which does't interfer with the user.
This plugin uses two methods to enable async actions in Vim- it will fall back to the second in the case of something going wrong with the first.

1. Vim Server- launch vim as a vim server.  You will also need to define `vim_executable exectable_name` in your ~/.floorc file. If you use MacVim, this is probably mvim for you.
2. We use an autocommand on CursorHold/CursorHoldI and then call feedkeys with f//e.  This will unfortuantely escape any key sequence you are doing unless you do it really quickly.  You can call :FlooPause/Unpause before them; alternatively, you can type your key sequences really quickly.  

Unfortunately, at the end of the day, Vim is purposefully designed to make async actions impossible.

## Installation

Assuming you have [Vundle](https://github.com/gmarik/vundle) or [Pathogen](https://github.com/tpope/vim-pathogen):

1. `cd ~/.vim/bundle` and `git clone https://github.com/Floobits/vim-plugin Floobits`
1. Vundle users: Add `Bundle 'Floobits'` to your `~/.vimrc`. Pathogen users should skip this step.
1. Add your Floobits username and API secret to `~/.floorc`.

A typical floorc looks like this:

    username myuser
    secret gii9Ka8aZei3ej1eighu2vi8D
    vim_executable mvim

## Usage

* To join a room, use `:FlooJoinRoom https://floobits.com/r/room_owner/room_name/`. Room urls are the same as what you see in the web editor.
* To part a room, use `:FlooPartRoom`.
* To toggle follow mode, use `:FlooToggleFollowMode`.
* To make everyone in the room jump to your cursor, use `:FlooPing`.

## Troubleshooting

Other plugins can interfere with Floobits. For example, [YouCompleteMe](https://github.com/Valloric/YouCompleteMe) changes `updatetime` to 2000 milliseconds. This causes increased latency and decreased reliability when collaborating. add `let g:ycm_allow_changing_updatetime = 0` to your `~/.vimrc`.

If you experience problems, try disabling other plugins before submitting a bug report.
