## What is the terminal?

<img src="/static/img/terminal.png" alt="This is a terminal" style="width:80%; height:auto;"/>


A **terminal** is a physical device with:
1. a screen 
2. a keyboard 
3. a connection to a computer. 

In their conception, terminals themselves would be fairly dumb (just the three aforementioned things, namely *not* a computer). Actual computation would be done on the (remote) computer to which the terminal is connected. The remote would have, crucially, a CPU (thus being a computer), as well as other important components, like storage.

Back when computers filled entire rooms, called mainframes, there might have been dozens or even hundreds of such terminals connected to a single computer, allowing multiple users to make use of the computer at once.

Some terminals [didn't even have a screen](/static/img/teletype.jpg), instead just having a printer. These kinds of terminals were often called "teletypes". It is from "teletype" that we get the abbreviation TTY. (Teletypes themselves had been used in "non-computer" applications for quite some time. They had begun life in the telegraph industry as a faster, more convenient way to send messages from one station to another than Morse code.)

Of course, nowadays we don't use dumb terminals very much. Instead we use programs that emulate one of these dumb terminals (and add a lot of features along the way, so they're not really dumb any more!). These are called **"terminal emulators"**.

When you run the Terminal program on your computer, you are starting up one of these terminal emulators. The terminal emulator runs a **shell** (e.g. Bash), which is a program that interprets the text written as some command. The shell is also an interpreter, and there are many of them. We cover in the next step. 

Many people will interchangably use the words:
- "terminal"
- "command prompt"
- "command line"
- "bash"
- "shell"  

As in "run this command in the terminal", or "this program runs on the command line", or "open a shell".

A **terminal** is a text-based way to interact with your computer.

- You type a command
- A program runs
- You see output

Most commands follow a pattern like:


```sh
command --options arguments
```


On macOS/Linux you usually use **bash** or **zsh**.
On Windows you might use **PowerShell**, **Command Prompt**, or **Git Bash**.
