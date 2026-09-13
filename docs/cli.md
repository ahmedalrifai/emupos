# emupos command reference

Simulate POS hardware at the wire-protocol level.

**Usage**:

```console
$ emupos [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--api URL`: Control API of the running simulator.  [env var: EMUPOS_API; default: http://127.0.0.1:8765]
* `--version`: Show the installed emupos version and exit.
* `--install-completion`: Install completion for the current shell.
* `--show-completion`: Show completion for the current shell, to copy it or customize the installation.
* `--help`: Show this message and exit.

**Commands**:

* `run`: Start the simulated devices and the...
* `devices`: List the running devices with their...
* `scan`: Scan a barcode, then wait until the...
* `doctor`: Check this machine and ./emupos.yaml for...
* `receipt`: Read the receipts a printer has completed.
* `scale`: Put weight on a scale, zero it or tare it.
* `fault`: Make a printer report a fault, or clear it.
* `drawer`: Act on a printer&#x27;s cash drawer.
* `barcode`: Generate barcodes that a POS decodes.
* `config`: Create, check and describe emupos.yaml.
* `setup`: Set up operating-system integrations.

## `emupos run`

Start the simulated devices and the control API, and show events live. Ctrl+C stops.

**Usage**:

```console
$ emupos run [OPTIONS]
```

**Options**:

* `--config PATH`: Configuration file. Default: emupos.yaml in the current directory.
* `--demo`: Use the built-in demo devices instead of a file.
* `--help`: Show this message and exit.

## `emupos devices`

List the running devices with their connections and current state.

**Usage**:

```console
$ emupos devices [OPTIONS]
```

**Options**:

* `--json`: Print one JSON document instead of text.
* `--help`: Show this message and exit.

## `emupos scan`

Scan a barcode, then wait until the simulator confirms it was typed or written.

**Usage**:

```console
$ emupos scan [OPTIONS] {data}
```

**Arguments**:

* `data`: The text the scanner reads, e.g. 6291041500213.  [required]

**Options**:

* `--device ID`: Device id. Optional when only one device of the type runs.
* `--countdown N`: Seconds before typing starts, to focus the POS.  [default: 3; x&gt;=0]
* `--unicode`: Type each character exactly, whatever the keyboard layout (for non-ASCII data).
* `--help`: Show this message and exit.

## `emupos doctor`

Check this machine and ./emupos.yaml for everything the simulator needs.

**Usage**:

```console
$ emupos doctor [OPTIONS]
```

**Options**:

* `--json`: Print one JSON document instead of text.
* `--help`: Show this message and exit.

## `emupos receipt`

Read the receipts a printer has completed.

**Usage**:

```console
$ emupos receipt [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `list`: List a printer&#x27;s receipts, newest first.
* `show`: Print a receipt as text; the latest one...

### `emupos receipt list`

List a printer&#x27;s receipts, newest first.

**Usage**:

```console
$ emupos receipt list [OPTIONS]
```

**Options**:

* `--device ID`: Device id. Optional when only one device of the type runs.
* `--json`: Print one JSON document instead of text.
* `--help`: Show this message and exit.

### `emupos receipt show`

Print a receipt as text; the latest one unless RECEIPT_ID is given.

**Usage**:

```console
$ emupos receipt show [OPTIONS] [RECEIPT_ID]
```

**Arguments**:

* `RECEIPT_ID`: Receipt id from `emupos receipt list`.  [default: latest]

**Options**:

* `--device ID`: Device id. Optional when only one device of the type runs.
* `--save PATH`: Also write the receipt image as PNG.
* `--json`: Print one JSON document instead of text.
* `--help`: Show this message and exit.

## `emupos scale`

Put weight on a scale, zero it or tare it.

**Usage**:

```console
$ emupos scale [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `set`: Set the weight on the scale, stable unless...
* `zero`: Zero the scale, as pressing its ZERO key...
* `tare`: Tare the scale: the current weight becomes...

### `emupos scale set`

Set the weight on the scale, stable unless --unstable is given.

**Usage**:

```console
$ emupos scale set [OPTIONS] {VALUE}
```

**Arguments**:

* `VALUE`: Gross weight: a number with the unit kg or g, e.g. 1.25kg or 1250g. Whole grams only. Negative values such as -100g are allowed (also written as `emupos scale set -- -100g`).  [required]

**Options**:

* `--device ID`: Device id. Optional when only one device of the type runs.
* `--unstable`: Report the weight as in motion until the scale settles.
* `--help`: Show this message and exit.

### `emupos scale zero`

Zero the scale, as pressing its ZERO key does.

**Usage**:

```console
$ emupos scale zero [OPTIONS]
```

**Options**:

* `--device ID`: Device id. Optional when only one device of the type runs.
* `--help`: Show this message and exit.

### `emupos scale tare`

Tare the scale: the current weight becomes the tare.

**Usage**:

```console
$ emupos scale tare [OPTIONS]
```

**Options**:

* `--device ID`: Device id. Optional when only one device of the type runs.
* `--help`: Show this message and exit.

## `emupos fault`

Make a printer report a fault, or clear it.

**Usage**:

```console
$ emupos fault [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `set`: Activate a fault, e.g.
* `clear`: Clear a fault, e.g.

### `emupos fault set`

Activate a fault, e.g. `emupos fault set front paper-out`.

**Usage**:

```console
$ emupos fault set [OPTIONS] {DEVICE} {FAULT}
```

**Arguments**:

* `DEVICE`: Printer id, e.g. front.  [required]
* `FAULT`: paper-near-end, paper-out, cover-open or offline.  [required]

**Options**:

* `--help`: Show this message and exit.

### `emupos fault clear`

Clear a fault, e.g. `emupos fault clear front paper-out`.

**Usage**:

```console
$ emupos fault clear [OPTIONS] {DEVICE} {FAULT}
```

**Arguments**:

* `DEVICE`: Printer id, e.g. front.  [required]
* `FAULT`: paper-near-end, paper-out, cover-open or offline.  [required]

**Options**:

* `--help`: Show this message and exit.

## `emupos drawer`

Act on a printer&#x27;s cash drawer.

**Usage**:

```console
$ emupos drawer [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `close`: Push the drawer shut.

### `emupos drawer close`

Push the drawer shut. The POS sees it closed on its next status request.

**Usage**:

```console
$ emupos drawer close [OPTIONS]
```

**Options**:

* `--device ID`: Device id. Optional when only one device of the type runs.
* `--help`: Show this message and exit.

## `emupos barcode`

Generate barcodes that a POS decodes. Works without the simulator.

**Usage**:

```console
$ emupos barcode [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `weighed`: Print the EAN-13 digits for a weighed or...

### `emupos barcode weighed`

Print the EAN-13 digits for a weighed or priced item, e.g.

emupos barcode weighed --layout weight-21 --item 12345 --weight 1.25kg

**Usage**:

```console
$ emupos barcode weighed [OPTIONS]
```

**Options**:

* `--layout PATTERN`: 13-character pattern such as 21IIIIIWWWWWC, or a preset: weight-21, price-23.  [required]
* `--item N`: Item code for the I field.  [required]
* `--weight VALUE`: Weight for a W field: a number with the unit kg or g, e.g. 1.25kg or 1250g.
* `--price MINOR`: Price for a P field, in minor units: 1299 is 12.99.
* `--save PATH`: Also write a PNG label with the digits beneath it.
* `--help`: Show this message and exit.

## `emupos config`

Create, check and describe emupos.yaml. None of these need the simulator.

**Usage**:

```console
$ emupos config [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `init`: Write a commented starter configuration.
* `validate`: Check a configuration file and list its...
* `schema`: Print the JSON Schema of emupos.yaml, for...

### `emupos config init`

Write a commented starter configuration. An existing file is never overwritten.

**Usage**:

```console
$ emupos config init [OPTIONS] [path]
```

**Arguments**:

* `path`: Configuration file. Default: emupos.yaml in the current directory.

**Options**:

* `--help`: Show this message and exit.

### `emupos config validate`

Check a configuration file and list its devices. Opens no ports and needs no simulator.

**Usage**:

```console
$ emupos config validate [OPTIONS] [path]
```

**Arguments**:

* `path`: Configuration file. Default: emupos.yaml in the current directory.

**Options**:

* `--help`: Show this message and exit.

### `emupos config schema`

Print the JSON Schema of emupos.yaml, for editor completion and validation.

**Usage**:

```console
$ emupos config schema [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

## `emupos setup`

Set up operating-system integrations.

**Usage**:

```console
$ emupos setup [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `print-queue`: Windows: create a print queue...

### `emupos setup print-queue`

Windows: create a print queue emupos-&lt;device id&gt; that sends raw jobs to a simulated printer.

**Usage**:

```console
$ emupos setup print-queue [OPTIONS]
```

**Options**:

* `--device ID`: Device id. Optional when only one device of the type runs.
* `--remove`: Delete the queue and port created for the printer.
* `--help`: Show this message and exit.
