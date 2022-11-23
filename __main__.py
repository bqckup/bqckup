from classes.bqckup import Bqckup

if __name__ == '__main__':
    try:
        Bqckup().backup()
    except Exception as e:
        print(f"Failed to running backup {e}")