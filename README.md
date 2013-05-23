# [Floobits](https://floobits.com/) Vim Plugin

Real-time collaborative editing. Think Etherpad, but with native editors. This is the plugin for Vim. We're also working on [Emacs](https://github.com/Floobits/emacs-plugin) and have a working plugin for [Sublime Text](https://github.com/Floobits/sublime-text-2-plugin) as well as a web based editor.

## Development status: fairly stable.  

Unfortunately, vim doesn't make it possible to have an event loop which does't interfer with the user.
This plugin uses two methods to enable async actions in Vim which have different side effects.  Floobits will fall back to the second in the case of something going wrong with the first.

1. Vim Server and --remote-expr.

To take advantage of this method, you should launch vim as a vim server.  Some versions of vim do this automatically, like MacVim.  On others, you may need to invoke vim like so:

`vim --servername superawesomename`

You will also need to define 

`vim_executable exectable_name `

in your ~/.floorc file. If you use MacVim, your floorc should probably contain the line:

`vim_executable mvim`

This option will sometimes call redraw which can make the minibuffer blink on ocassion.

2. CursorHold/CursorHoldI with feedkeys.

If your Vim wasn't launched as a server, or something goes wrong, floobits falls back to making an event loop by repeatedly triggering autocommands.
This will unfortuantely escape any key sequence, like ctrl-w j, unless you finish it within one tick of the event loop.  You can call 
`:FlooPause and :FlooUnpause 
before them.  Alternatively, you can type really quickly.  

Unfortunately, at the end of the day, Vim is purposefully designed to make async actions impossible and these are the only options available.

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
