import snowflake from 'snowflake-sdk';
import * as fs from 'fs';
import * as path from 'path';

let connection: snowflake.Connection | null = null;
let initialized = false;

const WAREHOUSE = process.env.SNOWFLAKE_WAREHOUSE || 'COMPUTE_WH';
const DATABASE = process.env.SNOWFLAKE_DATABASE || 'DBAPI_REPLICA_DB';

export async function getSnowflakeConnection(): Promise<snowflake.Connection> {
  if (connection) return connection;

  return new Promise((resolve, reject) => {
    const config: snowflake.ConnectionOptions = {
      account: process.env.SNOWFLAKE_ACCOUNT!,
      username: process.env.SNOWFLAKE_USER!,
      warehouse: WAREHOUSE,
      database: DATABASE,
      role: process.env.SNOWFLAKE_ROLE || 'ACCOUNTADMIN',
    };

    if (process.env.SNOWFLAKE_PRIVATE_KEY_PATH) {
      try {
        const privateKey = fs.readFileSync(process.env.SNOWFLAKE_PRIVATE_KEY_PATH, 'utf-8');
        config.authenticator = 'SNOWFLAKE_JWT';
        config.privateKey = privateKey;
      } catch (e) {
        console.error('Failed to read private key from SNOWFLAKE_PRIVATE_KEY_PATH:', e);
      }
    } else if (process.env.SNOWFLAKE_PASSWORD && process.env.SNOWFLAKE_PASSWORD !== 'placeholder') {
      config.password = process.env.SNOWFLAKE_PASSWORD;
    } else {
      const keyPaths = [
        path.join(process.cwd(), 'keys', 'rsa_key.p8'),
        '/app/keys/rsa_key.p8',
        '/keys/rsa_key.p8',
      ];
      
      for (const keyPath of keyPaths) {
        if (fs.existsSync(keyPath)) {
          try {
            const privateKey = fs.readFileSync(keyPath, 'utf-8');
            config.authenticator = 'SNOWFLAKE_JWT';
            config.privateKey = privateKey;
            console.log('Using RSA key from:', keyPath);
            break;
          } catch (e) {
            console.error('Failed to read key from', keyPath, e);
          }
        }
      }
    }

    if (!config.password && !config.privateKey) {
      reject(new Error('No Snowflake authentication configured. Set SNOWFLAKE_PASSWORD or provide RSA key.'));
      return;
    }

    console.log('Connecting to Snowflake:', { account: config.account, database: config.database, warehouse: config.warehouse });
    const conn = snowflake.createConnection(config);

    conn.connect((err, conn) => {
      if (err) {
        console.error('Snowflake connection error:', err.message);
        reject(err);
      } else {
        console.log('Snowflake connected successfully');
        connection = conn;
        resolve(conn);
      }
    });
  });
}

async function ensureContext(conn: snowflake.Connection): Promise<void> {
  if (initialized) return;
  
  return new Promise((resolve, reject) => {
    conn.execute({
      sqlText: `USE WAREHOUSE ${WAREHOUSE}`,
      complete: (err) => {
        if (err) {
          console.error('Failed to set warehouse:', err.message);
        }
        conn.execute({
          sqlText: `USE DATABASE ${DATABASE}`,
          complete: (err2) => {
            if (err2) {
              console.error('Failed to set database:', err2.message);
            }
            initialized = true;
            resolve();
          }
        });
      }
    });
  });
}

export async function executeQuery<T = Record<string, unknown>>(sql: string): Promise<T[]> {
  try {
    const conn = await getSnowflakeConnection();
    await ensureContext(conn);
    
    return new Promise((resolve, reject) => {
      conn.execute({
        sqlText: sql,
        complete: (err, stmt, rows) => {
          if (err) {
            console.error('Query error:', err.message);
            console.error('SQL:', sql.substring(0, 200));
            reject(err);
          } else {
            resolve((rows || []) as T[]);
          }
        }
      });
    });
  } catch (err) {
    console.error('Failed to execute query:', err);
    throw err;
  }
}

export async function testConnection(): Promise<{ connected: boolean; error?: string }> {
  try {
    const conn = await getSnowflakeConnection();
    await ensureContext(conn);
    await executeQuery('SELECT 1 as test');
    return { connected: true };
  } catch (err) {
    return { connected: false, error: (err as Error).message };
  }
}
