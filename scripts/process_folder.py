from serff_intel.cli import main


if __name__ == "__main__":
    main(["import-folder", *(__import__("sys").argv[1:])])

