from classes.bqckup import Bqckup

if __name__ == '__main__':
    try:
        Bqckup().do_backup("ab641000-e869-4f0f-9dfc-27c56756ebf7.yml")
    except Exception as e:
        print(e)