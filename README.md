# [Floobits](https://floobits.com/) Vim Plugin

Real-time collaborative editing. Think Etherpad, but with native editors. This is the plugin for Vim. We also have plugins for [Emacs](https://github.com/Floobits/floobits-emacs) and [Sublime Text](https://github.com/Floobits/floobits-sublime), as well as a web-based editor.

## Development status: fairly stable.

Unfortunately, Vim's plugin API has few options for running event-driven code. We've figured out two ways, which are described below. Floobits will fall back to the second method if something goes wrong with the first.

## 1. Vim Server and --remote-expr (Recommended)

To take advantage of this method, you should launch Vim as a server.  Some versions of Vim do this automatically, like MacVim.  On others, you may need to invoke Vim like so:

`vim --servername superawesomename`

You will also need to define `vim_executable exectable_name` in your ~/.floorc file. If you use MacVim, your floorc should contain the line:

`vim_executable mvim`

This option will sometimes call redraw, which can make the minibuffer blink on ocassion.

## 2. CursorHold/CursorHoldI with feedkeys.

If your Vim wasn't launched as a server, or something goes wrong, floobits falls back to making an event loop by repeatedly triggering autocommands.
This will unfortuantely escape any key sequence, like ctrl-w j, unless you finish it within one tick of the event loop.  You can call  `:FlooPause` and `:FlooUnpause` to pause/unpause the event loop if you have to. Alternatively, you can type really quickly.

Unfortunately, at the end of the day, Vim is purposefully designed to make async actions impossible and these are the only options available.


## Installation

* [Create a Floobits account](https://floobits.com/signup/) or [sign in with GitHub](https://floobits.com/login/github/?next=/dash/).
* Add your Floobits username and API secret to `~/.floorc`. You can find your API secret on [your settings page](https://floobits.com/dash/settings/). A typical `~/.floorc` looks like this:

```
username myuser
secret gii9Ka8aZei3ej1eighu2vi8D
vim_executable mvim
```

* [Vundle](https://github.com/gmarik/vundle) users: Add `Bundle 'Floobits/floobits-vim'` to your `~/.vimrc`. 
* [Pathogen](https://github.com/tpope/vim-pathogen) users: `cd ~/.vim/bundle` and `git clone https://github.com/Floobits/floobits-vim Floobits`


## Usage

* `:FlooShareDir /path/to/files`. Share a directory with others. This will create a new room, populate it with the files in that directory, and open the room's settings in your browser.
* `:FlooJoinRoom https://floobits.com/r/room_owner/room_name/`. Join a Floobits room. Room URLs are the same as what you see in the web editor.
* `:FlooPartRoom`. Leave the room.
* `:FlooToggleFollowMode`. Toggle follow mode. Follow mode will follow the most recent changes to buffers.
* `:FlooSummon`. Make everyone in the room jump to your cursor.
* `:FlooPause`. Pause the event loop so you can type keyboard shortcuts. (Only necessary in feedkeys fall-back mode.)
* `:FlooUnPause`. Resume the event loop so you can collaborate again. (Only necessary in feedkeys fall-back mode.)
* `:FlooDeleteBuf`. Delete the current buffer from the room.


## Troubleshooting

Other plugins can interfere with Floobits. For example, [YouCompleteMe](https://github.com/Valloric/YouCompleteMe) changes `updatetime` to 2000 milliseconds. This causes increased latency and decreased reliability when collaborating. add `let g:ycm_allow_changing_updatetime = 0` to your `~/.vimrc`.

If you experience problems, try disabling other plugins before [submitting a bug report](https://github.com/Floobits/floobits-vim/issues).
