#!/usr/bin/env python
# coding: utf-8

import logger, logging, errno
import threading, socket, sys, time, mysql.connector
from mysql.connector import errorcode as errorDB
from multiprocessing import Process, Queue
import multiprocessing

HOST = '150.16.21.40'
PORT = 50000

# Configuration de la base de données MySQL
dbConfig = {'user' : 'root',
            'password' : 'polinno',
            'host' : 'localhost',
            'database' : 'dispobox'}

all_data_table = "stats"


# Etat actuel des box (utilité à démontrer)
current_state = {'0' : '-1',
        '41' : '-1',
        '42' : '-1',
        '43' : '-1',
        '44' : '-1',
        '45' : '-1',
        '46' : '-1',
        '47' : '-1',
        '48' : '-1',
        '61' : '-1',
        '62' : '-1',
        '63' : '-1',
        '64' : '-1',
        '65' : '-1',
        '66' : '-1',
        '67' : '-1',
        '68' : '-1'}


"""
    A chaque nouvelle conexxion, cette fonction est appelée par un nouveau process.
    Tant que la connexion est en place, la fonction reçoit les données du client, puis met à jour 
    l'état des box grâce à create_new_state, puis les stock dans la queue.
"""
def active_connexion(myConnexion, myAdress, q):
    LOG.info("Client connecté, adresse IP %s, port %s" % (myAdress[0], myAdress[1]))
    connected = True
    while connected:
        nbit = 65
        for i in range(1,nbit+1):
            if (i<nbit):
                myConnexion.send("#")
            else:
                print("Demande d'infos")
                myConnexion.send("infos#")
                try:
                    msgClient = myConnexion.recv(1024)
                except Exception as e:
                    LOG.error("Exception renvoyée lors de la reception des données : "+str(e))
                if msgClient:
                    LOG.info("Message Recu : "+ msgClient)
                    if (msgClient!="rien"):
                        treat_msg_received(msgClient,q)
                else:
                    #Si la connexion s'est arretée, on détruit le process en cours
                    connected = False
        #except:
        #    raise
        #    LOG.error("CRASH DANS LE PROCESS :"+ multiprocessing.current_process())
        #    connected = False
        #    pass
            time.sleep(0.05)
    LOG.info("Connexion perdue avec %s" %(myAdress[0]))


"""
    Cette fonction est appelée par chaque process de connexion dès qu'un message est reçu. 
    Pour chaque message, elle sépare le numero du box et son état et renvoie le couple [nom, état]
"""
def treat_msg_received(msgClient,q):
    box_nb = ["0","0","0","0"]
    box_state = ["-1","-1","-1","-1"]
    nb_box = int(msgClient[0])
    print("nb de box ayant changé = "+str(nb_box))
    for i in range(1,nb_box+1):
        box_nb[i-1] = msgClient[3*i-2] + msgClient[3*i-1]
        box_state[i-1]= msgClient[3*i]
        q.put([box_nb[i-1],box_state[i-1]])
        LOG.debug("Nouvel état dans la queue : box "+ box_nb[i-1]+ " état "+box_state[i-1])

    """
    msg1 = True
    box_nb = ''
    box_state = ''
    for c in msgClient:
        if c == ';':
            msg1 = False
        else:
            if msg1:
                box_nb = box_nb + c
            else:
                box_state = box_state + c
    q.put([box_nb, box_state])
    return [box_nb, box_state]
    """

"""
    Boucle attendant une nouvelle connexion et créant un nouveau process lançant la fonction active_connexion
    dès qu'un nouveau matériel se connecte au réseau TCP.
    Cette boucle s'arrète dès que le thread principal active l'event "stop_event"
"""
def wait_connexion(stop_event, sock, state_q):
    while not stop_event.is_set():
        LOG.info("Attente d'une nouvelle connexion")
        sock.listen(5)
        try:
            connexion, adresse = sock.accept() # Attend la prochaine connexion
            p = Process(target = active_connexion, args=(connexion, adresse, state_q,))
            p.start()
        except Exception as e:
            if e.errno != 22: #22 est l'exception renvoyée lorsque la connexion est coupée par l'utilisateur
                LOG.error("Exception renvoyée lors de la reception des données : "+str(e))
            break           
    LOG.debug("Fin du thread pour la connexion")
    #On ferme les process
    p.terminate()


"""
    Boucle qui tourne en permanence dans un thread distinct. 
    Dès qu'un nouvel element est ajouté à la queue, le récupère et met à jour l'état des box
    dans le dictionnaire et dans la base de données SQL.
    Un event permet de terminer ce thread lorsqu'on arrête le programme.
"""
def MAJ_current_state(sql_connexion, stop_event, q, cursor):
    while not stop_event.is_set():
        new_state = q.get()
        current_state[new_state[0]] = new_state[1]
        try:
            cursor.execute("UPDATE current_state SET state = "+ new_state[1] +" WHERE name ="+ new_state[0])
        except mysql.connector.Error as err:
            LOG.error("Erreur lors de la MAJ de la BDD : ",str(err))
        sql_connexion.commit()

        store_complete_datas(cursor)
        time.sleep(0.5)
    LOG.debug("Sortie du thread de MAJ de la queue")



"""
    Fonction qui permet de stocker l'état général du système et l'heure à laquelle il a changé
    
"""
def store_complete_datas(cursor):
    # On cree la requete SDQL ne premiere fois
    SQL_order = "INSERT INTO "+all_data_table+" (`0`,"             # syntaxe de debut et champ '0'
    for i in range(41,48)+range(61,67):
        SQL_order += "`"+str(i)+"`,"                               # champs 41 à 67                        
    SQL_order += "`68`) VALUES ("+str(current_state['0'])+","      # champs 68, syntax des valeurs et valeur 0
    for j in range(41,48)+range(61,67):
        SQL_order = SQL_order + str(current_state[str(j)])+","     # valeurs 41 à 67
    SQL_order = SQL_order+str(current_state['68'])+");"            # valeur 68
    cursor.execute(SQL_order)
    


LOG=logger.create_logger()
LOG.info("##################################################")
LOG.info("#######         Lancement du serveur        ######") 
LOG.info("##################################################")


# Connexion au serveur MySQL
try:
    sql_con = mysql.connector.connect(**dbConfig)
    cursor = sql_con.cursor()
except mysql.connector.Error as err :
    if err.errno == errorDB.ER_ACCESS_DENIED_ERROR:
        LOG.error("L'utilisateur ou le mot de passe mysql n'est pas le bon.")
    elif err.errno == errorDB.ER_BAD_DB_ERROR:
        LOG.error("La base de données demandée n'existe pas sur ce serveur")
    else:
        LOG.error(str(err))
sql_con.commit()


# Creation du socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    sock.bind((HOST,PORT))
except socket.error, msg:
    LOG.error("La liaison du socket a échoué : "+ str(msg))
    sys.exit()
    

# Creation de la queue
state_q = Queue()

LOG.info("Serveur prêt")
print "Appuyez sur n'importe quelle touche pour arreter le programme"

# informe la BDD que le système est en marche
current_state["0"] = 1
cursor.execute("UPDATE current_state SET state = 1 WHERE name = 00")
store_complete_datas(cursor)
sql_con.commit()

stop_event = threading.Event()
connex_thread = threading.Thread(target = wait_connexion, args=(stop_event, sock, state_q, ))
connex_thread.daemon = True
connex_thread.start()
maj_state_thread = threading.Thread(target = MAJ_current_state, args=(sql_con, stop_event, state_q, cursor, ))
maj_state_thread.daemon = True
maj_state_thread.start()

# Fin du programme lorsqu'on tape une touche dans le terminal.
keyPressed = raw_input()
LOG.info("Fin du programme demandée par l'utilisateur")
print("#######           EXITING PROGRAM           ######")
print("##################################################")


#cursor.execute("UPDATE current_state SET state = -1 WHERE name = 0")
cursor.execute("UPDATE current_state SET state = -1")
current_state["0"]= -1
store_complete_datas(cursor)
sql_con.commit()

stop_event.set()
sock.shutdown(2)
sock.close()
LOG.info("Socket closed")
sql_con.close()
LOG.info("Connexion sql closed")
sys.exit()
