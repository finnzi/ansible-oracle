// PROTOTYPE: proves TAC replay and FAN/FCF with the bundled Oracle 19c client.
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.Properties;
import java.util.concurrent.atomic.AtomicBoolean;

import oracle.simplefan.FanEventListener;
import oracle.simplefan.FanManager;
import oracle.simplefan.FanSubscription;
import oracle.simplefan.LoadAdvisoryEvent;
import oracle.simplefan.NodeDownEvent;
import oracle.simplefan.ServiceDownEvent;
import oracle.ucp.jdbc.PoolDataSource;
import oracle.ucp.jdbc.PoolDataSourceFactory;

public final class TacFcfPoc {
    private static String scalar(Connection connection, String sql) throws Exception {
        try (PreparedStatement statement = connection.prepareStatement(sql);
             ResultSet rows = statement.executeQuery()) {
            if (!rows.next()) {
                throw new IllegalStateException("Query returned no rows: " + sql);
            }
            return rows.getString(1);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 6) {
            System.err.println("Usage: TacFcfPoc <url> <user> <password> <service> <ons-nodes> <token>");
            System.exit(64);
        }

        String url = args[0];
        String user = args[1];
        String password = args[2];
        String service = args[3];
        String onsNodes = args[4];
        String token = args[5];
        AtomicBoolean fanDown = new AtomicBoolean(false);

        FanManager fanManager = FanManager.getInstance();
        Properties fanConfiguration = new Properties();
        fanConfiguration.setProperty("onsNodes", onsNodes);
        fanManager.configure(fanConfiguration);
        Properties subscriptionProperties = new Properties();
        subscriptionProperties.setProperty("serviceName", service);
        FanSubscription subscription = fanManager.subscribe(subscriptionProperties);
        subscription.addListener(new FanEventListener() {
            public void handleEvent(ServiceDownEvent event) {
                fanDown.set(true);
                System.out.println("FAN_DOWN|" + event.getServiceName() + "|"
                    + event.getDatabaseUniqueName() + "|" + event.getReason());
                System.out.flush();
            }

            public void handleEvent(NodeDownEvent event) {
                System.out.println("FAN_NODE_DOWN|" + event.getNodeName());
                System.out.flush();
            }

            public void handleEvent(LoadAdvisoryEvent event) {
                // Load events are not part of this single-instance proof.
            }
        });

        PoolDataSource pool = PoolDataSourceFactory.getPoolDataSource();
        pool.setConnectionPoolName("TacFcfPocPool");
        pool.setConnectionFactoryClassName("oracle.jdbc.replay.OracleDataSourceImpl");
        pool.setURL(url);
        pool.setUser(user);
        pool.setPassword(password);
        pool.setONSConfiguration("nodes=" + onsNodes);
        pool.setFastConnectionFailoverEnabled(true);
        pool.setInitialPoolSize(1);
        pool.setMinPoolSize(1);
        pool.setMaxPoolSize(4);
        pool.setValidateConnectionOnBorrow(true);
        pool.setConnectionWaitTimeout(120);

        try (Connection connection = pool.getConnection()) {
            String initialDatabase = scalar(connection,
                "select sys_context('USERENV','DB_UNIQUE_NAME') from dual");
            System.out.println("POC_READY|db=" + initialDatabase
                + "|fcf=" + pool.getFastConnectionFailoverEnabled()
                + "|available=" + pool.getAvailableConnectionsCount()
                + "|borrowed=" + pool.getBorrowedConnectionsCount());
            System.out.println("TAC_CALL_BEGIN|" + token);
            System.out.flush();

            long started = System.currentTimeMillis();
            try (CallableStatement statement = connection.prepareCall(
                    "begin tac_fcf_test.do_work(?); end;")) {
                statement.setString(1, token);
                statement.execute();
            }
            long elapsed = System.currentTimeMillis() - started;
            String finalDatabase = scalar(connection,
                "select sys_context('USERENV','DB_UNIQUE_NAME') from dual");
            String count = scalar(connection,
                "select count(*) from tac_fcf_test.results where token = '"
                    + token.replace("'", "''") + "'");
            System.out.println("TAC_CALL_OK|db=" + finalDatabase + "|count=" + count
                + "|elapsed_ms=" + elapsed);
        }

        try (Connection replacement = pool.getConnection()) {
            String database = scalar(replacement,
                "select sys_context('USERENV','DB_UNIQUE_NAME') from dual");
            System.out.println("FCF_BORROW_OK|db=" + database
                + "|available=" + pool.getAvailableConnectionsCount()
                + "|borrowed=" + pool.getBorrowedConnectionsCount());
        }

        for (int i = 0; i < 20 && !fanDown.get(); i++) {
            Thread.sleep(500L);
        }
        subscription.close();
        System.out.println("POC_RESULT|fan_down=" + fanDown.get()
            + "|fcf=" + pool.getFastConnectionFailoverEnabled());
        System.out.flush();
        if (!fanDown.get()) {
            System.exit(2);
        }
    }
}
